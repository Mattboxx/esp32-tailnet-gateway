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
structurally only. STA overload shedding is compiled with a 64-slot TCPIP
mailbox model: frame classification on real header bytes, the 48-slot
threshold, priority frames in the last 16 slots, a full mailbox and recovery
after draining. NETIF_SANITIZE=1 on Linux adds ASan/UBSan.
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
shed = between(hooks, '/* Overload shedding on the STA input path', 'return ethernet_input(p, netif);\n}\n')
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
assert 'int budget = ML_NET_IO_DRAIN_BUDGET(ml->disco_sock4);' in drain
assert '#define ML_NET_IO_DRAIN_BUDGET(fd) (ml_at_socket_is_at_fd(fd) ? 1 : ML_NET_IO_DRAIN_MAX)' in netio
assert 'drained ? MSG_DONTWAIT : 0' in drain and 'if (n <= 0)\n                break;' in drain
assert '#define ML_NET_IO_DRAIN_MAX 16' in netio
rx_input = wg.index('if (device->netif->input(pbuf, device->netif) == ERR_OK) {')
assert wg.index('wg_tx_count_drop(&s_wg_rx_input_refused);', rx_input) - rx_input < 200
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
#include <string.h>
struct pbuf { uint16_t tot_len; int freed; void *payload; uint16_t len; };
struct netif { int id; uint8_t flags; uint32_t ip; };
#define NETIF_FLAG_ETHARP 0x08U
#define NETIF_FLAG_ETHERNET 0x40U
#define netif_ip4_addr(n) (&(n)->ip)
#define ip4_addr_get_u32(a) (*(a))
#define CONFIG_LWIP_TCPIP_RECVMBOX_SIZE 64
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
/* TCPIP thread model: a 64-slot mailbox of (frame, handler); tcpip_input is only an identity. */
static err_t tcpip_input(struct pbuf *p, struct netif *n) { (void)p; (void)n; return ERR_VAL; }
static unsigned eth_calls;
static err_t ethernet_input(struct pbuf *p, struct netif *n) { (void)p; (void)n; eth_calls++; return ERR_OK; }
static uint16_t web_port_now = 8080;
static uint16_t web_ui_active_port(void) { return web_port_now; }
static struct { struct pbuf *p; struct netif *n; netif_input_fn fn; } box[64];
static unsigned box_n;
static err_t tcpip_inpkt(struct pbuf *p, struct netif *n, netif_input_fn fn) {
    if (box_n >= 64) return ERR_MEM;
    box[box_n].p = p; box[box_n].n = n; box[box_n].fn = fn; box_n++;
    return ERR_OK;
}
static void tcpip_drain(void) { for (unsigned i = 0; i < box_n; i++) box[i].fn(box[i].p, box[i].n); box_n = 0; }
#include <limits.h>
#include <stddef.h>
#define REJECT_AFTER_MESSAGES (0xFFFFFFFFFFFFFFFFULL - (1ULL << 13))
struct wireguard_keypair { uint64_t replay_counter; uint32_t replay_bitmap; };
'''

tests = r'''
int main(void) {
    struct netif sta = {.id = 1};
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
    /* Overload shedding: classification of actual frame bytes. */
    {
        const uint32_t own = 0x0201a8c0u;           /* 192.168.1.2, network byte order */
        static uint8_t fr[64][80];
        static struct pbuf pb[64];
        #define FRAME(i, type, dst, proto, dport, frag) do { \
            memset(fr[i], 0, sizeof fr[i]); fr[i][12] = (uint8_t)((type) >> 8); fr[i][13] = (uint8_t)(type); \
            fr[i][14] = 0x45; fr[i][14 + 6] = (uint8_t)(frag); fr[i][14 + 9] = (proto); \
            uint32_t d_ = (dst); memcpy(fr[i] + 14 + 16, &d_, 4); \
            fr[i][14 + 20 + 2] = (uint8_t)((dport) >> 8); fr[i][14 + 20 + 3] = (uint8_t)(dport); \
            pb[i] = (struct pbuf){ .tot_len = 80, .payload = fr[i], .len = 80 }; } while (0)
        FRAME(0, 0x0806, 0, 0, 0, 0);             assert(netif_hooks_sta_frame_priority(&pb[0], own, 8080));  /* ARP */
        FRAME(1, 0x86dd, 0, 0, 0, 0);             assert(netif_hooks_sta_frame_priority(&pb[1], own, 8080));  /* IPv6 */
        FRAME(2, 0x0800, 0x0a0a0a0au, 6, 443, 0); assert(!netif_hooks_sta_frame_priority(&pb[2], own, 8080)); /* forwarded */
        FRAME(3, 0x0800, 0xffffffffu, 17, 67, 0); assert(netif_hooks_sta_frame_priority(&pb[3], own, 8080));  /* broadcast */
        FRAME(4, 0x0800, 0xfb0000e0u, 17, 5353, 0); assert(netif_hooks_sta_frame_priority(&pb[4], own, 8080)); /* multicast */
        FRAME(5, 0x0800, own, 17, 41641, 0);      assert(netif_hooks_sta_frame_priority(&pb[5], own, 8080));  /* WireGuard */
        FRAME(6, 0x0800, own, 1, 0, 0);           assert(netif_hooks_sta_frame_priority(&pb[6], own, 8080));  /* ICMP */
        FRAME(7, 0x0800, own, 6, 8080, 0);        assert(netif_hooks_sta_frame_priority(&pb[7], own, 8080));  /* web UI */
        FRAME(8, 0x0800, own, 6, 50000, 0);       assert(netif_hooks_sta_frame_priority(&pb[8], own, 8080));  /* own client */
        FRAME(9, 0x0800, own, 6, 8443, 0);        assert(!netif_hooks_sta_frame_priority(&pb[9], own, 8080)); /* service port */
        FRAME(10, 0x0800, own, 6, 8443, 0x01);    assert(netif_hooks_sta_frame_priority(&pb[10], own, 8080)); /* later fragment */
        FRAME(13, 0x0800, own, 6, 8443, 0x20);    assert(!netif_hooks_sta_frame_priority(&pb[13], own, 8080)); /* first fragment: has the port */
        assert(!netif_hooks_sta_frame_priority(&pb[7], own, 0));   /* web UI not listening */
        pb[11] = pb[9]; pb[11].len = 20;          assert(netif_hooks_sta_frame_priority(&pb[11], own, 8080)); /* short */
        fr[12][0] = 0; FRAME(12, 0x0800, own, 6, 8443, 0); fr[12][14] = 0x44;
        assert(netif_hooks_sta_frame_priority(&pb[12], own, 8080));                                         /* bad IHL */
        assert(netif_hooks_sta_frame_priority(NULL, own, 8080));
        /* The counted path: 48 bulk frames queue, the 49th is shed; priority frames use
         * the remaining 16 slots; a full mailbox still refuses; draining restores. */
        original_sta_input = tcpip_input;
        struct netif nif = { .id = 2, .flags = NETIF_FLAG_ETHARP, .ip = own };
        uint32_t refused0 = netif_hooks_get_sta_input_refused();
        for (int i = 0; i < 48; i++) { FRAME(i, 0x0800, 0x0a0a0a0au, 6, 443, 0); assert(sta_input_hook(&pb[i], &nif) == ERR_OK); }
        assert(box_n == 48 && s_sta_queued == 48 && netif_hooks_get_sta_input_shed() == 0);
        FRAME(48, 0x0800, 0x0a0a0a0au, 6, 443, 0);
        assert(sta_input_hook(&pb[48], &nif) == ERR_OK && pb[48].freed == 1 && box_n == 48);
        assert(netif_hooks_get_sta_input_shed() == 1 && s_sta_queued == 48);
        FRAME(49, 0x0800, own, 6, 8443, 0);         /* service port: shed too */
        assert(sta_input_hook(&pb[49], &nif) == ERR_OK && pb[49].freed == 1 && netif_hooks_get_sta_input_shed() == 2);
        for (int i = 50; i < 64; i++) { FRAME(i, 0x0800, own, 17, 41641, 0); assert(sta_input_hook(&pb[i], &nif) == ERR_OK); }
        FRAME(48, 0x0800, own, 6, 8080, 0);         /* web UI request still queues */
        assert(sta_input_hook(&pb[48], &nif) == ERR_OK && box_n == 63);
        FRAME(49, 0x0800, own, 1, 0, 0);
        assert(sta_input_hook(&pb[49], &nif) == ERR_OK && box_n == 64 && s_sta_queued == 64);
        FRAME(14, 0x0800, own, 17, 41641, 0);
        assert(sta_input_hook(&pb[14], &nif) == ERR_MEM && s_sta_queued == 64 && !pb[14].freed); /* mailbox full */
        assert(netif_hooks_get_sta_input_refused() == refused0 + 1 && netif_hooks_get_sta_input_shed() == 2);
        tcpip_drain();
        assert(eth_calls == 64 && s_sta_queued == 0);
        FRAME(0, 0x0800, 0x0a0a0a0au, 6, 443, 0);   /* below the threshold bulk passes again */
        assert(sta_input_hook(&pb[0], &nif) == ERR_OK && box_n == 1 && s_sta_queued == 1);
        tcpip_drain();
        assert(s_sta_queued == 0 && eth_calls == 65);
        /* A netif without Ethernet framing keeps the original input. */
        original_sta_input = driver_input; driver_result = ERR_OK;
        struct netif raw = { .id = 3, .flags = 0, .ip = own };
        unsigned before = driver_in;
        assert(sta_input_hook(&pb[2], &raw) == ERR_OK && driver_in == before + 1 && box_n == 0);
        #undef FRAME
    }
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
    /* Decrypted packets refused by netif->input */
    assert(wireguardif_rx_input_refused() == 0);
    for (int i = 0; i < 3; i++) wg_tx_count_drop(&s_wg_rx_input_refused);
    assert(wireguardif_rx_input_refused() == 3);
    /* wg_rx_queue full drops */
    assert(microlink_wg_rx_queue_drops() == 0);
    for (int i = 0; i < 7; i++) ml_count_wg_rx_queue_drop();
    assert(microlink_wg_rx_queue_drops() == 7);
    puts("PASS: STA refused-input/output counters (success, ACL drop, missing original, 37 refusals), WireGuard TX drop counters and call-site placement, RX sequence gap/late counters (gap, late fill, duplicate, jump, limit), wg_rx_queue drop counter, STA overload shedding (frame classes, 48-slot threshold, priority slots, full mailbox, drain); drain loop structural");
}
'''

with tempfile.TemporaryDirectory(prefix='drop-counters-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + counters + '\n' + shed + '\n' + sta_in + '\n' + sta_out + '\n' + wg_counters + '\n'
                                 + replay + '\n' + queue_drops + '\n' + tests,
                                 encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get('NETIF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
