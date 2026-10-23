"""mDNS probing on an uplink without IPv6 addresses (host, actual lwIP code).

The firmware never assigns IPv6 addresses to its Wi-Fi uplink. lwIP 2.2.0's
responder (as shipped in ESP-IDF 5.5.3) advances probing only when both the
IPv4 and the IPv6 probe are sent, so on a real board it probed every 250 ms
forever and never answered "<name>.local". Compiles the actual
mdns_probe_and_announce() of the SDK file (expected to stay stuck: documents
the reason for the patch) and of main/lwip_mdns/mdns.c (must complete), with
fixtures for the netif, timers and probe transmission. MDNS_SANITIZE=1 adds
ASan/UBSan. MDNS_SDK_DIR overrides the pinned SDK lwIP mdns folder.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(os.environ.get('MDNS_SDK_DIR', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/lwip/lwip/src/apps/mdns')))


def c_func(src, signature):
    body = signature + src.split(signature, 1)[1]
    depth, out = 0, []
    for ch in body:
        out.append(ch)
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return ''.join(out)
    raise AssertionError(signature)


def constant(src, name):
    return src.split('#define ' + name, 1)[1].split('\n', 1)[0].strip()


patched = (ROOT / 'main/lwip_mdns/mdns.c').read_text(encoding='utf-8')
original = (SDK / 'mdns.c').read_text(encoding='utf-8')
SIG = 'static void\nmdns_probe_and_announce(void* arg)\n'
HAS6 = 'static int\nmdns_netif_has_ip6(struct netif *netif)\n'
# The copy must equal the SDK file apart from the header note and the patch.
assert 'mdns_netif_has_ip6' not in original, 'the SDK changed: review main/lwip_mdns/mdns.c'
stripped = patched.replace('\r\n', '\n').split('*/\n', 1)[1]
for piece in (c_func(stripped.replace('\r\n', '\n'), HAS6),):
    stripped = stripped.replace('#if LWIP_IPV6\n' + piece + '\n#endif\n\n', '', 1)
stripped = stripped.replace(
    """        /* ESP32 Tailnet Gateway patch: an interface without a valid IPv6
         * address cannot send the IPv6 probe (no source address); upstream
         * then retries forever and never answers. Probe IPv4 only there. */
        if (!mdns_netif_has_ip6(netif) || mdns_send_probe(netif, &v6group) == ERR_OK)""",
    """        if (mdns_send_probe(netif, &v6group) == ERR_OK)""", 1)
assert stripped == original.replace('\r\n', '\n'), 'main/lwip_mdns/mdns.c differs from the SDK beyond the documented patch'

fixture = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define LWIP_IPV4 1
#define LWIP_IPV6 1
#define LWIP_IPV6_NUM_ADDRESSES 3
typedef int8_t err_t; typedef uint32_t u32_t; typedef uint8_t u8_t; typedef int8_t s8_t;
#define ERR_OK 0
#define ERR_RTE -4
#define MDNS_PROBE_COUNT ''' + constant(original, 'MDNS_PROBE_COUNT') + r'''
#define MDNS_ANNOUNCE_COUNT ''' + constant(original, 'MDNS_ANNOUNCE_COUNT') + r'''
#define MDNS_ANNOUNCE_DELAY_MS 1000
#define MDNS_PROBE_DELAY_MS 250
#define MDNS_PROBE_MAX_CONFLICTS_TIMEOUT 5000
#define MDNS_PROBING_SUCCESSFUL 1
typedef enum { MDNS_STATE_OFF, MDNS_STATE_PROBE_WAIT, MDNS_STATE_PROBING, MDNS_STATE_ANNOUNCE_WAIT, MDNS_STATE_ANNOUNCING, MDNS_STATE_COMPLETE } mdns_resp_state;
typedef struct { uint32_t addr; } ip4_addr_t;
typedef struct { int family; } ip_addr_t;
struct netif { ip4_addr_t ip4; u8_t ip6_state[LWIP_IPV6_NUM_ADDRESSES]; void *host; };
struct mdns_host { mdns_resp_state state; u8_t sent_num; u8_t rate_limit_activated; };
#define NETIF_TO_HOST(n) ((struct mdns_host *)(n)->host)
#define netif_ip4_addr(n) (&(n)->ip4)
#define ip4_addr_isany_val(a) ((a).addr == 0)
#define netif_ip6_addr_state(n, i) ((n)->ip6_state[i])
#define ip6_addr_isvalid(s) (((s) & 0x30) != 0)
static const ip_addr_t v4group = {4}, v6group = {6};
static int probes4, probes6, announces, success_cb;
static err_t mdns_send_probe(struct netif *n, const ip_addr_t *g) {
    if (g == &v4group) { probes4++; return ERR_OK; }
    for (int i = 0; i < LWIP_IPV6_NUM_ADDRESSES; i++) if (ip6_addr_isvalid(n->ip6_state[i])) { probes6++; return ERR_OK; }
    return ERR_RTE;   /* lwIP: no IPv6 source address on this netif */
}
static void mdns_resp_announce(struct netif *n) { (void)n; announces++; }
typedef void (*mdns_name_result_cb_t)(struct netif *, u8_t, s8_t);
static void on_result(struct netif *n, u8_t r, s8_t s) { (void)n; (void)s; if (r == MDNS_PROBING_SUCCESSFUL) success_cb++; }
static mdns_name_result_cb_t mdns_name_result_cb = on_result;
typedef void (*sys_timeout_handler)(void *);
static sys_timeout_handler pending; static void *pending_arg; static u32_t pending_ms;
static void sys_timeout(u32_t ms, sys_timeout_handler h, void *a) { pending = h; pending_arg = a; pending_ms = ms; }
'''

tests = r'''
static int run(struct netif *n, int max_timers) {
    struct mdns_host *h = n->host; h->state = MDNS_STATE_PROBE_WAIT; h->sent_num = 0;
    probes4 = probes6 = announces = success_cb = 0;
    pending = mdns_probe_and_announce; pending_arg = n;
    int fired = 0;
    while (pending && fired < max_timers) { sys_timeout_handler f = pending; pending = NULL; f(pending_arg); fired++; }
    return fired;
}
int main(void) {
    struct mdns_host host = {0};
    struct netif v4only = {.ip4 = {0x0a01a8c0}, .host = &host};
    int fired = run(&v4only, 1000);
#ifdef EXPECT_STUCK
    assert(fired == 1000 && host.state == MDNS_STATE_PROBE_WAIT && host.sent_num == 0 && probes4 == 1000 && announces == 0 && pending_ms == MDNS_PROBE_DELAY_MS);
    puts("PASS: SDK lwIP mDNS on an IPv4-only uplink stays in probing (1000 timer runs, no answers): the reason for the patch (host)");
#else
    assert(host.state == MDNS_STATE_COMPLETE && probes4 == MDNS_PROBE_COUNT && probes6 == 0);
    assert(announces == MDNS_ANNOUNCE_COUNT && success_cb == 1 && !pending && fired < 10);
    /* No IPv4 address yet: keep waiting, never complete. */
    struct netif none = {.ip4 = {0}, .host = &host};
    run(&none, 50); assert(host.state == MDNS_STATE_PROBE_WAIT && probes4 == 0 && announces == 0);
    /* Dual-stack interface: both probes required, as upstream. */
    struct netif dual = {.ip4 = {0x0a01a8c0}, .ip6_state = {0x30, 0, 0}, .host = &host};
    run(&dual, 1000); assert(host.state == MDNS_STATE_COMPLETE && probes4 == MDNS_PROBE_COUNT && probes6 == MDNS_PROBE_COUNT);
    /* Tentative-only IPv6 address (not valid yet): treated as IPv4-only. */
    struct netif tentative = {.ip4 = {0x0a01a8c0}, .ip6_state = {0x08, 0, 0}, .host = &host};
    run(&tentative, 1000); assert(host.state == MDNS_STATE_COMPLETE && probes6 == 0);
    puts("PASS: patched lwIP mDNS completes probing and announces on an IPv4-only uplink, waits without IPv4, keeps dual-stack probing (host)");
#endif
    return 0;
}
'''

for label, source, extra in (('sdk', original, ['-DEXPECT_STUCK']), ('patched', patched.replace('\r\n', '\n'), [])):
    functions = (c_func(source, HAS6) + '\n' if label == 'patched' else '') + c_func(source, SIG)
    with tempfile.TemporaryDirectory(prefix='lan-mdns-') as directory:
        path = Path(directory)
        (path / 'test.c').write_text(fixture + functions + tests, encoding='utf-8')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', *extra]
        if os.environ.get('MDNS_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        binary = path / ('test.exe' if os.name == 'nt' else 'test')
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
