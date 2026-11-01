"""Actual STA hook, WireGuard TX and RX loss counters, compiled from the sources.

No device or network access. Checks that a frame refused after the ACL is
counted once and handed back (the refusing caller frees it), that ACL drops,
successes and a missing original are not counted as saturation, and the
WireGuard counter accessor. The WireGuard call sites sit inside the large
output function, so only their position is checked structurally (stated, not
a behaviour test). The RX side compiles the actual replay check with its
sequence-gap counters and the wg_rx_queue drop accessor. The replay cases
are: in order, gaps, late fills, duplicates, rekey-size jumps and the
counting limit. The socket drain loop in the net I/O task is checked
structurally only. NETIF_SANITIZE=1 on Linux adds ASan/UBSan.
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

ML = ROOT / 'external/microlink/components/microlink'
wgc = (ML / 'components/wireguard_lwip/src/wireguard.c').read_text(encoding='utf-8').replace('\r\n', '\n')
mlc = (ML / 'src/microlink.c').read_text(encoding='utf-8').replace('\r\n', '\n')
netio = (ML / 'src/ml_net_io.c').read_text(encoding='utf-8').replace('\r\n', '\n')
derp = (ML / 'src/ml_derp.c').read_text(encoding='utf-8').replace('\r\n', '\n')
replay = between(wgc, '#define WG_RX_GAP_MAX', '\treturn result;\n}\n')
queue_drops = between(mlc, 'static volatile uint32_t s_wg_rx_queue_drops;',
                      'return __atomic_load_n(&s_wg_rx_queue_drops, __ATOMIC_RELAXED); }')

# Structural (not behaviour): the WG/DISCO socket is drained per select(), AT
# sockets read once, and both full-queue paths count the drop.
drain = between(netio, 'if (ml->disco_sock4 >= 0 && FD_ISSET(ml->disco_sock4, &read_fds)) {',
                'route_udp_packet(ml, pkt_data, n, src_ip, src_port);')
assert 'ml_at_socket_is_at_fd(ml->disco_sock4) ? 1 : ML_NET_IO_DRAIN_MAX' in drain
assert 'drained ? MSG_DONTWAIT : 0' in drain and 'if (n <= 0)\n                break;' in drain
assert '#define ML_NET_IO_DRAIN_MAX 16' in netio
assert 'ml_count_wg_rx_queue_drop();' in between(netio, 'case PKT_WIREGUARD:', 'free(data);  /* Queue full, drop */')
assert 'if (target == ml->wg_rx_queue)\n            ml_count_wg_rx_queue_drop();' in between(
    derp, 'if (xQueueSend(target, &pkt, 0) != pdTRUE) {', 'free(data);')

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
#include <limits.h>
#include <stddef.h>
#define REJECT_AFTER_MESSAGES (0xFFFFFFFFFFFFFFFFULL - (1ULL << 13))
struct wireguard_keypair { uint64_t replay_counter; uint32_t replay_bitmap; };
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
    /* RX sequence gaps: in order, a gap of 5, a late fill, a duplicate, a rekey-size jump, the limit. */
    struct wireguard_keypair kp = {0};
    uint32_t gap = 9, late = 9;
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 0 && late == 0);
    for (uint64_t s = 0; s < 100; s++) assert(wireguard_check_replay(&kp, s));
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 0 && late == 0);
    assert(wireguard_check_replay(&kp, 105));               /* 100..104 missing */
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 5 && late == 0);
    assert(wireguard_check_replay(&kp, 102));               /* arrives late: accepted */
    assert(!wireguard_check_replay(&kp, 102));              /* duplicate: rejected, not counted */
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 5 && late == 1);
    uint64_t top = 105 + 5001;
    assert(wireguard_check_replay(&kp, top));               /* rekey-size jump: not counted */
    assert(!wireguard_check_replay(&kp, 103));              /* far behind the window now */
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 5 && late == 1);
    assert(wireguard_check_replay(&kp, top + 1025));        /* 1024 skipped: the limit, counted */
    assert(wireguard_check_replay(&kp, top + 1025 + 1026)); /* 1025 skipped: not counted */
    wireguard_rx_seq_stats(&gap, &late);
    assert(gap == 5 + 1024 && late == 1);
    assert(!wireguard_check_replay(&kp, REJECT_AFTER_MESSAGES));
    wireguard_rx_seq_stats(NULL, &late); wireguard_rx_seq_stats(&gap, NULL); wireguard_rx_seq_stats(NULL, NULL);
    /* wg_rx_queue full drops */
    assert(microlink_wg_rx_queue_drops() == 0);
    for (int i = 0; i < 7; i++) ml_count_wg_rx_queue_drop();
    assert(microlink_wg_rx_queue_drops() == 7);
    puts("PASS: STA refused-input/output counters (success, ACL drop, missing original, 37 refusals), WireGuard TX drop counters and call-site placement, RX sequence gap/late counters (gap, late fill, duplicate, jump, limit), wg_rx_queue drop counter; drain loop structural");
}
'''

with tempfile.TemporaryDirectory(prefix='drop-counters-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + counters + '\n' + sta_in + '\n' + sta_out + '\n' + wg_counters + '\n'
                                 + replay + '\n' + queue_drops + '\n' + tests,
                                 encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get('NETIF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
