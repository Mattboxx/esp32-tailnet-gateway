"""WireGuard data-path copies (3.0.7-beta.9): actual MicroLink C on the host.

- process_wg_packet(): in zero-copy mode the dispatcher receives a PBUF_REF
  whose payload IS the queued buffer, the buffer is still intact during the
  call and freed exactly once after it; the copy mode (kept for -prof
  measurements) still copies; allocation failures free the buffer once;
  relay packets get the "any" source address.
- wg_rx_preload_next(): the priority lane is peeked first, nothing happens
  when the variant is off, the queues are empty, the buffer is not in SPIRAM
  or the previous preload is still running; the range is 64-byte aligned and
  covers the whole packet; the previous preload is ended before a new one.
- wg_tx_zero_unwritten(): the bytes that reach the encryption are identical
  to the former "zero everything, then copy" for every plaintext length,
  keepalives and a pbuf longer than the message; the plaintext area is not
  written twice.
Also checks that decryption no longer zeroes the plaintext first and that a
short pbuf copy on transmit cannot leave stale bytes.
Host fixtures replace lwIP, FreeRTOS queues and the ROM cache routines.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
mgr = (ML / 'src/ml_wg_mgr.c').read_text(encoding='utf-8').replace('\r\n', '\n')
wg = (ML / 'components/wireguard_lwip/src/wireguardif.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


process = function(mgr, 'static void process_wg_packet(')
preload = function(mgr, 'static void wg_rx_preload_next(')
zero = function(wg, 'static void wg_tx_zero_unwritten(')
assert 'ml_rx_packet_t next;' in preload and 'wg_rx_preload_next(ml);\n            process_wg_packet(ml, &wg_pkt);' in mgr
assert mgr.count('wg_rx_preload_next(ml);') == 2
rx = wg[wg.index('static void wireguardif_process_data_message('):]
rx = rx[:rx.index('\n}\n')]
assert 'memset(pbuf->payload, 0, pbuf->tot_len)' not in wg, 'whole-buffer zeroing is gone'
assert 'bool decrypt_ok = wireguard_decrypt_packet(pbuf->payload, src, src_len, nonce, keypair);' in rx
assert 'if (copied < unpadded_len) memset(dst + copied, 0, unpadded_len - copied);' in wg
assert 'wg_tx_zero_unwritten(pbuf->payload, header_len, unpadded_len, padded_len, pbuf->tot_len);' in wg
assert '#define ML_RX_PRELOAD()   0' in mgr, 'release images keep the preload off until measured'

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t u16_t;
typedef int BaseType_t;
#define pdTRUE 1
#define pdFALSE 0
#define ESP_LOGD(...) ((void)0)
#define ML_PERF_US(...) ((void)0)
#define ML_PERF_NOW_US() 0
#define ML_PERF_BEGIN(x) ((void)0)
#define ML_PERF_END(...) ((void)0)
#define WIREGUARD_AUTHTAG_LEN 16
enum {PBUF_RAW = 0, PBUF_RAM = 1, PBUF_REF = 2, IPADDR_TYPE_V4 = 4};
struct pbuf {void *payload; uint16_t len, tot_len; int type; void *owned;};
typedef struct {int type; uint32_t addr;} ip_addr_t;
#define IP_SET_TYPE_VAL(a, t) ((a).type = (t))
#define ip_2_ip4(a) (a)
static void ip4_addr_set_u32(ip_addr_t *a, uint32_t v) {a->addr = v;}
static void ip_addr_set_any(bool v6, ip_addr_t *a) {assert(!v6); a->type = 4; a->addr = 0;}
static uint32_t htonl(uint32_t v) {return __builtin_bswap32(v);}
struct netif {void *state;};
typedef struct {uint8_t *data; size_t len; bool via_derp; uint32_t src_ip; uint16_t src_port; uint8_t src_pubkey[32]; uint64_t enq_us;} ml_rx_packet_t;
typedef struct {ml_rx_packet_t items[4]; int n;} queue_t;
typedef queue_t *QueueHandle_t;
typedef struct {struct netif *wg_netif; QueueHandle_t wg_rx_prio_queue, wg_rx_queue;} microlink_t;

/* Allocation fixtures. */
static void *live[8]; static int frees, pbuf_frees, fail_alloc;
static void *track(void *p) {for (int i = 0; i < 8; i++) if (!live[i]) {live[i] = p; return p;} abort();}
static void untrack(void *p) {for (int i = 0; i < 8; i++) if (live[i] == p) {live[i] = NULL; return;} assert(!"double or foreign free");}
static void test_free(void *p) {if (!p) return; untrack(p); memset(p, 0xdd, 4); free(p); frees++;}
#define free test_free
static struct pbuf *pbuf_alloc(int layer, uint16_t len, int type) {
    assert(layer == PBUF_RAW);
    if (fail_alloc) return NULL;
    struct pbuf *p = track(calloc(1, sizeof *p));
    p->len = p->tot_len = len; p->type = type;
    if (type == PBUF_RAM) p->payload = p->owned = track(malloc(len));
    return p;
}
static void pbuf_take(struct pbuf *p, const void *data, uint16_t len) {assert(len == p->len); memcpy(p->payload, data, len);}
static void pbuf_free(struct pbuf *p) {if (p->owned) test_free(p->owned); test_free(p); frees--; pbuf_frees++;}

/* Dispatcher fixture: synchronous, frees p like wireguardif_network_rx(). */
static int rx_calls; static uint8_t *expect_payload; static uint8_t first_byte; static uint32_t seen_addr; static int seen_type;
static void wireguardif_network_rx(void *dev, void *pcb, struct pbuf *p, const ip_addr_t *addr, u16_t port) {
    (void)pcb; (void)port; assert(dev);
    rx_calls++;
    if (expect_payload) assert(p->payload == expect_payload && p->type == PBUF_REF);
    else assert(p->type == PBUF_RAM);
    first_byte = ((uint8_t *)p->payload)[0];
    seen_addr = addr->addr; seen_type = addr->type;
    pbuf_free(p);
}
static int zero_copy = 1, preload_on = 1;
#define ML_RX_ZERO_COPY() (zero_copy)
#define ML_RX_PRELOAD() (preload_on)

/* Queue and ROM cache fixtures for the preload. */
static BaseType_t xQueuePeek(QueueHandle_t q, ml_rx_packet_t *out, int wait) {
    (void)wait; if (!q->n) return pdFALSE; *out = q->items[0]; return pdTRUE;
}
static int external = 1, done = 1, starts, ends; static uint32_t start_addr, start_size;
static bool esp_ptr_external_ram(const void *p) {(void)p; return external;}
static uint32_t Cache_DCache_Preload_Done(void) {return done;}
static void Cache_End_DCache_Preload(uint32_t a) {assert(a == 0); ends++;}
static uint32_t Cache_Start_DCache_Preload(uint32_t addr, uint32_t size, uint32_t order) {
    assert(order == 0); assert(ends == starts + 1); starts++; start_addr = addr; start_size = size; return 0;
}
''' + process + preload + '\n#undef free\n' + zero + r'''
static uint8_t *queued(size_t n, uint8_t first) {uint8_t *d = track(malloc(n)); memset(d, 0x11, n); d[0] = first; return d;}
int main(void) {
    struct netif nif = {.state = (void *)1}; queue_t prio = {0}, bulk = {0};
    microlink_t ml = {.wg_netif = &nif, .wg_rx_prio_queue = &prio, .wg_rx_queue = &bulk};
    /* Zero-copy: the dispatcher sees the queued buffer, then it is freed once. */
    ml_rx_packet_t pkt = {.data = queued(1400, 0x04), .len = 1400, .src_ip = 0x0a000001, .src_port = 41641};
    expect_payload = pkt.data; frees = pbuf_frees = 0;
    process_wg_packet(&ml, &pkt);
    assert(rx_calls == 1 && first_byte == 0x04 && frees == 1 && pbuf_frees == 1 && seen_addr == htonl(0x0a000001));
    /* Relay packet: "any" source. */
    pkt = (ml_rx_packet_t){.data = queued(148, 0x01), .len = 148, .via_derp = true};
    expect_payload = pkt.data; process_wg_packet(&ml, &pkt);
    assert(seen_addr == 0 && seen_type == 4 && rx_calls == 2);
    /* Copy mode (-prof comparisons): a PBUF_RAM copy, buffer freed before dispatch. */
    zero_copy = 0; expect_payload = NULL; frees = 0;
    pkt = (ml_rx_packet_t){.data = queued(1400, 0x04), .len = 1400};
    process_wg_packet(&ml, &pkt);
    assert(rx_calls == 3 && first_byte == 0x04 && frees == 2);   /* the buffer and the copy */
    /* Allocation failure in both modes: buffer freed once, no dispatch. */
    for (zero_copy = 0; zero_copy <= 1; zero_copy++) {
        fail_alloc = 1; frees = 0;
        pkt = (ml_rx_packet_t){.data = queued(64, 0x04), .len = 64};
        process_wg_packet(&ml, &pkt);
        assert(frees == 1 && rx_calls == 3);
        fail_alloc = 0;
    }
    /* No netif / no device: buffer freed once. */
    nif.state = NULL; frees = 0; pkt = (ml_rx_packet_t){.data = queued(64, 0x04), .len = 64};
    process_wg_packet(&ml, &pkt); assert(frees == 1 && rx_calls == 3); nif.state = (void *)1;
    for (int i = 0; i < 8; i++) assert(!live[i]);

    /* Preload: off, empty, priority first, alignment, busy, internal RAM. */
    static uint8_t area[4096] __attribute__((aligned(64)));
    preload_on = 0; bulk.items[0] = (ml_rx_packet_t){.data = area + 70, .len = 1400}; bulk.n = 1;
    wg_rx_preload_next(&ml); assert(starts == 0);
    preload_on = 1; bulk.n = 0; wg_rx_preload_next(&ml); assert(starts == 0);
    bulk.n = 1; wg_rx_preload_next(&ml);
    assert(starts == 1 && start_addr == (uint32_t)(uintptr_t)(area + 64) && start_addr % 64 == 0);
    assert(start_addr + start_size >= (uint32_t)(uintptr_t)(area + 70 + 1400) && start_size % 64 == 0 && start_size <= 1472);
    prio.items[0] = (ml_rx_packet_t){.data = area + 2048, .len = 100}; prio.n = 1;
    wg_rx_preload_next(&ml); assert(starts == 2 && start_addr == (uint32_t)(uintptr_t)(area + 2048) && start_size == 128);
    done = 0; wg_rx_preload_next(&ml); assert(starts == 2); done = 1;
    external = 0; wg_rx_preload_next(&ml); assert(starts == 2); external = 1;
    prio.items[0].len = 0; wg_rx_preload_next(&ml); assert(starts == 2);

    /* TX zeroing equals the former full zeroing for what is encrypted and sent. */
    for (size_t plain = 0; plain <= 70; plain++) {
        for (size_t extra = 0; extra <= 8; extra += 8) {
            size_t padded = (plain + 15) & ~(size_t)15, out_len = 16 + padded + 16, tot = out_len + extra;
            uint8_t before[128], after[128], text[80];
            for (size_t i = 0; i < plain; i++) text[i] = (uint8_t)(i * 7 + 3);
            memset(before, 0, tot); memcpy(before + 16, text, plain);
            memset(after, 0xaa, tot);
            wg_tx_zero_unwritten(after, 16, plain, padded, tot);
            for (size_t i = 16; i < 16 + plain; i++) assert(after[i] == 0xaa);   /* not written twice */
            memcpy(after + 16, text, plain);
            assert(!memcmp(before, after, 16 + padded));                         /* header + plaintext + padding */
            assert(!memcmp(before + out_len, after + out_len, extra));           /* past the tag */
        }
    }
    puts("PASS: zero-copy RX hand-off (queued buffer passed, intact during dispatch, freed once after), copy mode, "
         "allocation and missing-device failures, relay source; next-packet DCache preload (priority lane first, "
         "off/empty/busy/internal-RAM skipped, 64-byte aligned full range); TX zeroing equal to full zeroing for "
         "0-70 byte plaintexts, keepalives and longer pbufs; no pre-decrypt zeroing; short TX copy padded (host)");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='wg-rx-path-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
