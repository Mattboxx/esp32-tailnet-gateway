"""DERP netcheck (actual MicroLink ml_netcheck.c) on a simulated clock and network.

The netcheck runs on the coordination task right after the first network
map and blocks the control session, the DERP relay and the first tunnel
until it ends. Board A (3.0.12-pre4/pre5 boot timeline) spent about 28 s in
it on every boot: the map itself took 0.15 s. The whole source after its
includes is compiled with stubs for sockets, DNS, time and logging; the
simulated network answers each STUN probe after the region's RTT, or never.
Checked:
- every region answers: the lowest-RTT region is picked, RTTs are stored per
  region, and the netcheck ends as soon as two samples per region arrived;
- one region silent (the usual case on board A): the netcheck ends within its
  budget (5 s plus DNS and send spacing), with the right pick; the former
  25 s budget fails this bound;
- every region silent: no pick (0), within the same bound;
- a first reply lost: the retry gets the region measured;
- a stop request ends it at once.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'external/microlink/components/microlink/src/ml_netcheck.c').read_text(encoding='utf-8').replace('\r\n', '\n')
BODY = SRC[SRC.index('static const char *TAG'):]
TIMEOUT_MS = int(re.search(r'#define NETCHECK_TIMEOUT_MS\s+(\d+)', SRC).group(1))

STUBS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
/* sockets, renamed so no host socket header can collide */
#define fd_set nc_fd_set
#define timeval nc_timeval
#define sockaddr nc_sockaddr
#define sockaddr_in nc_sockaddr_in
#define addrinfo nc_addrinfo
#define socklen_t nc_socklen_t
#define select nc_select
#define socket nc_socket
#define bind nc_bind
#define sendto nc_sendto
#define recvfrom nc_recvfrom
#define close nc_close
#define getaddrinfo nc_getaddrinfo
#define freeaddrinfo nc_freeaddrinfo
#define htons nc_htons
typedef int nc_socklen_t;
typedef struct { int set; } nc_fd_set;
#undef FD_ZERO
#undef FD_SET
#define FD_ZERO(s) ((s)->set = 0)
#define FD_SET(fd, s) ((s)->set = 1)
struct nc_timeval { long tv_sec; long tv_usec; };
struct nc_in_addr { uint32_t s_addr; };
struct nc_sockaddr { int sa_family; };
struct nc_sockaddr_in { int sin_family; uint16_t sin_port; struct nc_in_addr sin_addr; };
struct nc_addrinfo { int ai_family, ai_socktype; struct nc_sockaddr *ai_addr; struct nc_addrinfo *ai_next; };
#define AF_INET 2
#define SOCK_DGRAM 2
static uint16_t nc_htons(uint16_t v) { return (uint16_t)((v << 8) | (v >> 8)); }
/* ESP-IDF */
#define ESP_LOGI(...) do { } while (0)
#define ESP_LOGW(...) do { } while (0)
#define ESP_OK 0
typedef int esp_err_t;
typedef struct { uint32_t addr; } esp_ip4_addr_t;
typedef struct { esp_ip4_addr_t ip, netmask, gw; } esp_netif_ip_info_t;
typedef struct esp_netif_obj esp_netif_t;
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *k) { (void)k; return NULL; }
static esp_err_t esp_netif_get_ip_info(esp_netif_t *n, esp_netif_ip_info_t *i) { (void)n; (void)i; return -1; }
static uint64_t now_us, stop_at_us = UINT64_MAX;
static int64_t esp_timer_get_time(void) { return (int64_t)now_us; }
static uint32_t rnd = 1;
static void esp_fill_random(uint8_t *b, size_t n) { for (size_t i = 0; i < n; i++) { rnd = rnd * 1103515245u + 12345u; b[i] = (uint8_t)(rnd >> 16); } }
static uint32_t esp_crc32_le(uint32_t c, const uint8_t *b, size_t n) { (void)b; (void)n; return c; }
typedef unsigned int EventBits_t;
typedef void *EventGroupHandle_t;
#define ML_EVT_SHUTDOWN_REQUEST 1u
static EventBits_t xEventGroupGetBits(EventGroupHandle_t g) { (void)g; return now_us >= stop_at_us ? ML_EVT_SHUTDOWN_REQUEST : 0; }
/* the MicroLink fields the netcheck uses */
#define ML_MAX_DERP_REGIONS 32
#define ML_MAX_DERP_NODES 4
typedef struct { char hostname[64]; uint16_t stun_port; } ml_derp_node_t;
typedef struct { uint16_t region_id; ml_derp_node_t nodes[ML_MAX_DERP_NODES]; uint8_t node_count; } ml_derp_region_t;
typedef struct {
    EventGroupHandle_t events;
    int derp_region_count;
    ml_derp_region_t derp_regions[ML_MAX_DERP_REGIONS];
    uint16_t derp_rtt_ms[ML_MAX_DERP_REGIONS];
    uint32_t stun_public_ip;
} microlink_t;
static void microlink_ip_to_str(uint32_t ip, char *s) { (void)ip; s[0] = 0; }
/* simulated network: region i (1-based id) at 10.0.0.i answers after rtt_ms[i] (<0 never);
 * drop_first[i] loses the first reply; DNS costs dns_ms per lookup */
static int rtt_ms[ML_MAX_DERP_REGIONS + 1], drop_first[ML_MAX_DERP_REGIONS + 1], sent[ML_MAX_DERP_REGIONS + 1];
static int dns_ms = 30;
#define MAXQ 512
static struct { uint64_t at; uint8_t txid[12]; int live; } q[MAXQ];
static int pending = -1;
static int nc_socket(int a, int b, int c) { (void)a; (void)b; (void)c; return 3; }
static int nc_bind(int s, const struct nc_sockaddr *a, int l) { (void)s; (void)a; (void)l; return 0; }
static int nc_close(int s) { (void)s; return 0; }
static int nc_sendto(int s, const void *buf, size_t len, int f, const struct nc_sockaddr *to, int tl) {
    (void)s; (void)len; (void)f; (void)tl;
    int region = (int)(((const struct nc_sockaddr_in *)to)->sin_addr.s_addr & 0xff);
    sent[region]++;
    if (rtt_ms[region] < 0) return 40;
    if (drop_first[region] && sent[region] == 1) return 40;
    for (int i = 0; i < MAXQ; i++) if (!q[i].live) {
        q[i].live = 1; q[i].at = now_us + (uint64_t)rtt_ms[region] * 1000u; memcpy(q[i].txid, (const uint8_t *)buf + 8, 12);
        return 40;
    }
    abort();
}
static int nc_select(int n, nc_fd_set *r, void *w, void *e, struct nc_timeval *tv) {
    (void)n; (void)r; (void)w; (void)e;
    uint64_t limit = now_us + (uint64_t)tv->tv_sec * 1000000u + (uint64_t)tv->tv_usec;
    int best = -1;
    for (int i = 0; i < MAXQ; i++) if (q[i].live && q[i].at <= limit && (best < 0 || q[i].at < q[best].at)) best = i;
    if (best < 0) { now_us = limit; return 0; }
    if (q[best].at > now_us) now_us = q[best].at;
    pending = best;
    return 1;
}
static int nc_recvfrom(int s, void *buf, size_t len, int f, struct nc_sockaddr *from, nc_socklen_t *fl) {
    (void)s; (void)len; (void)f; (void)from; (void)fl;
    if (pending < 0) return -1;
    uint8_t *b = buf;
    memset(b, 0, 20);
    b[0] = 0x01; b[1] = 0x01; b[4] = 0x21; b[5] = 0x12; b[6] = 0xA4; b[7] = 0x42;
    memcpy(b + 8, q[pending].txid, 12);
    q[pending].live = 0; pending = -1;
    return 20;
}
static struct nc_sockaddr_in dns_addr;
static struct nc_addrinfo dns_res = { AF_INET, SOCK_DGRAM, (struct nc_sockaddr *)&dns_addr, NULL };
static int nc_getaddrinfo(const char *h, const char *s, const struct nc_addrinfo *hints, struct nc_addrinfo **res) {
    (void)s; (void)hints;
    now_us += (uint64_t)dns_ms * 1000u;
    dns_addr.sin_addr.s_addr = 0x0000000Au | ((uint32_t)atoi(h + 1) << 24);
    dns_addr.sin_addr.s_addr = (uint32_t)atoi(h + 1);   /* low byte = region id */
    *res = &dns_res;
    return 0;
}
static void nc_freeaddrinfo(struct nc_addrinfo *r) { (void)r; }
'''

DRIVER = r'''
static microlink_t ml;
static void setup(int regions) {
    memset(&ml, 0, sizeof ml); memset(q, 0, sizeof q); memset(sent, 0, sizeof sent); memset(drop_first, 0, sizeof drop_first);
    now_us = 0; stop_at_us = UINT64_MAX; pending = -1;
    ml.events = (void *)1;
    ml.derp_region_count = regions;
    for (int i = 0; i < regions; i++) {
        ml.derp_regions[i].region_id = (uint16_t)(i + 1);
        ml.derp_regions[i].node_count = 1;
        snprintf(ml.derp_regions[i].nodes[0].hostname, 64, "r%d", i + 1);
        rtt_ms[i + 1] = 40 + 13 * ((i * 7) % 11);
    }
}
int main(void) {
    const int R = 28;
    /* 1. every region answers */
    setup(R); rtt_ms[9] = 21;
    uint16_t best = ml_netcheck_pick_best_derp(&ml);
    uint64_t t1 = now_us / 1000;
    if (best != 9 || ml.derp_rtt_ms[8] != 21 || ml.derp_rtt_ms[0] == 0) { printf("FAIL all-answer pick %u\n", best); return 1; }
    /* 2. one region silent */
    setup(R); rtt_ms[9] = 21; rtt_ms[5] = -1;
    best = ml_netcheck_pick_best_derp(&ml);
    uint64_t t2 = now_us / 1000;
    if (best != 9 || ml.derp_rtt_ms[4] != 0) { printf("FAIL one-silent pick %u\n", best); return 1; }
    /* 3. every region silent */
    setup(R); for (int i = 1; i <= R; i++) rtt_ms[i] = -1;
    best = ml_netcheck_pick_best_derp(&ml);
    uint64_t t3 = now_us / 1000;
    if (best != 0) { printf("FAIL all-silent pick %u\n", best); return 1; }
    /* 4. first reply lost, the retry measures it */
    setup(R); for (int i = 1; i <= R; i++) rtt_ms[i] = 200; rtt_ms[3] = 15; drop_first[3] = 1;
    best = ml_netcheck_pick_best_derp(&ml);
    if (best != 3 || sent[3] < 2) { printf("FAIL lost-first pick %u sent %d\n", best, sent[3]); return 1; }
    /* 5. stop request */
    setup(R); for (int i = 1; i <= R; i++) rtt_ms[i] = -1; stop_at_us = 2000000;
    best = ml_netcheck_pick_best_derp(&ml);
    uint64_t t5 = now_us / 1000;
    printf("%llu %llu %llu %llu %u\n", (unsigned long long)t1, (unsigned long long)t2, (unsigned long long)t3,
           (unsigned long long)t5, best);
    return 0;
}
'''


def run(body):
    with tempfile.TemporaryDirectory(prefix='netcheck-') as folder:
        path = Path(folder)
        (path / 'nc.c').write_text(STUBS + body + DRIVER, encoding='utf-8')
        exe = path / ('nc.exe' if os.name == 'nt' else 'nc')
        flags = ['-std=gnu11', '-O1', '-Wall', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-but-set-variable']
        if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'nc.c'), '-o', str(exe)], check=True)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        return [int(x) for x in out.stdout.split()]


R = 28
dns = 30 * R
spacing = 50 * R          # probes are spaced 50 ms apart, retries too
bound = dns + 5000 + 4 * spacing + 500
t1, t2, t3, t5, stop_best = run(BODY)
assert t1 <= dns + 2 * spacing + 1500, f'all regions answered but the netcheck took {t1} ms'
assert t2 <= bound, f'one silent region kept the netcheck for {t2} ms (bound {bound} ms)'
assert t3 <= bound, f'all silent: {t3} ms (bound {bound} ms)'
assert t5 <= 2000 + 300 and stop_best == 0, f'stop request not honoured quickly ({t5} ms)'
# the former 25 s budget fails the bound
old = BODY.replace(f'#define NETCHECK_TIMEOUT_MS    {TIMEOUT_MS}', '#define NETCHECK_TIMEOUT_MS    25000') \
          .replace('#define NETCHECK_RETRY_GAP_MS  1000', '#define NETCHECK_RETRY_GAP_MS  5000')
if old != BODY:
    o2 = run(old)[1]
    assert o2 > bound, f'the 25 s budget was expected to exceed the bound ({o2} ms)'
print(f'netcheck: all answer {t1} ms, one region silent {t2} ms, all silent {t3} ms (bound {bound} ms with {R} regions), '
      f'lowest RTT picked, lost first reply retried, stop honoured in {t5} ms')
