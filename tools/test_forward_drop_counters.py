"""Actual STA hook and WireGuard TX drop counters, compiled from the sources.

No device or network access. Checks that a frame refused after the ACL is
counted once and handed back (the refusing caller frees it), that ACL drops,
successes and a missing original are not counted as saturation, and the
WireGuard counter accessor. The WireGuard call sites sit inside the large
output function, so only their position is checked structurally (stated, not
a behaviour test). NETIF_SANITIZE=1 on Linux adds ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
hooks = (ROOT / 'main/netif_hooks.c').read_text(encoding='utf-8').replace('\r\n', '\n')
wg = (ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/wireguardif.c'
      ).read_text(encoding='utf-8').replace('\r\n', '\n')


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i) + len(end)]


counters = between(hooks, '/* Saturation counters for the STA path', 'return s_sta_output_refused; }')
sta_in = between(hooks, 'static err_t sta_input_hook', '\n}\n')
sta_out = between(hooks, 'static err_t sta_linkoutput_hook', '\n}\n')
wg_counters = between(wg, '/* Transport-data packets lost on the way out',
                      '*alloc_failed = __atomic_load_n(&s_wg_tx_alloc_failed, __ATOMIC_RELAXED);\n}\n')

send_call = wg.index('result = wireguardif_peer_output(netif, pbuf, peer);')
assert wg.index('if (result != ERR_OK) wg_tx_count_drop(&s_wg_tx_send_failed);', send_call) - send_call < 200
alloc = wg.index('// Failed to allocate memory\n\t\t\t\twg_tx_count_drop(&s_wg_tx_alloc_failed);')
assert wg.rindex('if (pbuf) {', 0, alloc) > send_call - 6000

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef int err_t;
#define ERR_OK 0
#define ERR_MEM -1
#define ERR_VAL -6
#define ACL_TO_ESP 1
#define ACL_FROM_ESP 2
struct pbuf { uint16_t tot_len; int freed; };
struct netif { int id; };
typedef err_t (*netif_input_fn)(struct pbuf *, struct netif *);
typedef err_t (*netif_linkoutput_fn)(struct netif *, struct pbuf *);
static netif_input_fn original_sta_input;
static netif_linkoutput_fn original_sta_linkoutput;
static volatile uint64_t s_sta_bytes_in, s_sta_bytes_out;
static bool acl_deny;
static unsigned driver_in, driver_out, ttl_calls;
static err_t driver_result;
static void pbuf_free(struct pbuf *p) { p->freed++; }
static inline uint8_t acl_check_and_tap(uint8_t list, struct pbuf *p, bool ap) { (void)list; (void)p; (void)ap; return acl_deny; }
static inline bool acl_drops(uint8_t action) { return action != 0; }
static inline void apply_sta_ttl_override(struct pbuf *p) { (void)p; ttl_calls++; }
static err_t driver_input(struct pbuf *p, struct netif *n) { (void)p; (void)n; driver_in++; return driver_result; }
static err_t driver_linkoutput(struct netif *n, struct pbuf *p) { (void)p; (void)n; driver_out++; return driver_result; }
'''

tests = r'''
int main(void) {
    struct netif sta = {1};
    struct pbuf p = {.tot_len = 1400};
    /* Initial state and a missing original: no saturation counted. */
    assert(netif_hooks_get_sta_input_refused() == 0 && netif_hooks_get_sta_output_refused() == 0);
    assert(sta_input_hook(&p, &sta) == ERR_VAL && sta_linkoutput_hook(&sta, &p) == ERR_VAL);
    assert(netif_hooks_get_sta_input_refused() == 0 && netif_hooks_get_sta_output_refused() == 0 && !p.freed);
    original_sta_input = driver_input; original_sta_linkoutput = driver_linkoutput;
    /* Accepted frames pass through uncounted. */
    driver_result = ERR_OK;
    for (int i = 0; i < 1000; i++) {
        assert(sta_input_hook(&p, &sta) == ERR_OK && sta_linkoutput_hook(&sta, &p) == ERR_OK);
    }
    assert(driver_in == 1000 && driver_out == 1000 && netif_hooks_get_sta_input_refused() == 0);
    /* ACL drops are policy, not saturation: freed on input, never reach the driver. */
    acl_deny = true;
    assert(sta_input_hook(&p, &sta) == ERR_OK && p.freed == 1 && driver_in == 1000);
    assert(sta_linkoutput_hook(&sta, &p) == ERR_OK && p.freed == 1 && driver_out == 1000);
    assert(netif_hooks_get_sta_input_refused() == 0 && netif_hooks_get_sta_output_refused() == 0);
    acl_deny = false; p.freed = 0;
    /* Refused by the next stage: counted once, error returned unchanged, not freed here. */
    driver_result = ERR_MEM;
    for (int i = 0; i < 37; i++) {
        assert(sta_input_hook(&p, &sta) == ERR_MEM);
        assert(sta_linkoutput_hook(&sta, &p) == ERR_MEM);
    }
    assert(netif_hooks_get_sta_input_refused() == 37 && netif_hooks_get_sta_output_refused() == 37 && !p.freed);
    assert(s_sta_bytes_in == 1039u * 1400u && s_sta_bytes_out == 1039u * 1400u && ttl_calls == 1039);
    /* WireGuard TX counters: zero, then exact counts; NULL outputs allowed. */
    uint32_t sent = 99, alloc = 99;
    wireguardif_tx_drops(&sent, &alloc);
    assert(sent == 0 && alloc == 0);
    for (int i = 0; i < 5; i++) wg_tx_count_drop(&s_wg_tx_send_failed);
    wg_tx_count_drop(&s_wg_tx_alloc_failed);
    wireguardif_tx_drops(&sent, &alloc);
    assert(sent == 5 && alloc == 1);
    wireguardif_tx_drops(NULL, &alloc); wireguardif_tx_drops(&sent, NULL); wireguardif_tx_drops(NULL, NULL);
    assert(sent == 5 && alloc == 1);
    puts("PASS: STA refused-input/output counters (success, ACL drop, missing original, 37 refusals), WireGuard TX drop counters and call-site placement");
}
'''

with tempfile.TemporaryDirectory(prefix='drop-counters-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + counters + '\n' + sta_in + '\n' + sta_out + '\n' + wg_counters + tests,
                                 encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get('NETIF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
