/* Faster IPv4 UDP/TCP checksum: see fast_chksum.h. */
#include "fast_chksum.h"

#include <string.h>
#include "lwip/def.h"
#include "lwip/inet_chksum.h"
#include "lwip/ip_addr.h"
#include "lwip/pbuf.h"
#include "lwip/prot/ip.h"
#include "esp_cpu.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_random.h"
#include "perf_hooks.h"

static const char *TAG = "fast_chksum";

/* fast_chksum_xtensa.S: the plain sum of nhalf 16-bit words at p, with
 * the vector unit (PIE) or the scalar zero-overhead loop. */
uint32_t tsr_csum_halfwords(const void *p, uint32_t nhalf);
uint32_t tsr_csum_halfwords_pie(const void *p, uint32_t nhalf);
/* The loop in use; chosen by fc_check() on the device. */
static uint32_t (*s_halfwords)(const void *p, uint32_t nhalf) = tsr_csum_halfwords;

#define FC_FOLD(u) (((u) >> 16) + ((u) & 0xffffUL))
#define FC_SWAP(w) ((((w) & 0xffUL) << 8) | (((w) & 0xff00UL) >> 8))

/* lwip_standard_chksum() of LWIP_CHKSUM_ALGORITHM 2, byte for byte, with
 * its one-word loop replaced by the Xtensa loop. */
static u16_t fc_standard(const void *dataptr, int len)
{
    const u8_t *pb = (const u8_t *)dataptr;
    u16_t t = 0;
    u32_t sum;
    int odd = ((uintptr_t)pb & 1);
    if (odd && len > 0) {
        ((u8_t *)&t)[1] = *pb++;
        len--;
    }
    sum = len > 1 ? s_halfwords(pb, (u32_t)len >> 1) : 0;
    if (len & 1) {
        ((u8_t *)&t)[0] = pb[len - 1];
    }
    sum += t;
    sum = FC_FOLD(sum);
    sum = FC_FOLD(sum);
    if (odd) {
        sum = FC_SWAP(sum);
    }
    return (u16_t)sum;
}

/* inet_chksum_pseudo() + inet_cksum_pseudo_base() of lwIP 2.1, unchanged
 * except for the per-pbuf sum. */
static u16_t fc_pseudo_v4(struct pbuf *p, u8_t proto, u16_t proto_len,
                          const ip4_addr_t *src, const ip4_addr_t *dest)
{
    u32_t addr = ip4_addr_get_u32(src);
    u32_t acc = (addr & 0xffffUL);
    acc = (u32_t)(acc + ((addr >> 16) & 0xffffUL));
    addr = ip4_addr_get_u32(dest);
    acc = (u32_t)(acc + (addr & 0xffffUL));
    acc = (u32_t)(acc + ((addr >> 16) & 0xffffUL));
    acc = FC_FOLD(acc);
    acc = FC_FOLD(acc);

    int swapped = 0;
    for (struct pbuf *q = p; q != NULL; q = q->next) {
        acc += fc_standard(q->payload, q->len);
        acc = FC_FOLD(acc);
        if (q->len % 2 != 0) {
            swapped = !swapped;
            acc = FC_SWAP(acc);
        }
    }
    if (swapped) {
        acc = FC_SWAP(acc);
    }
    acc += (u32_t)lwip_htons((u16_t)proto);
    acc += (u32_t)lwip_htons(proto_len);
    acc = FC_FOLD(acc);
    acc = FC_FOLD(acc);
    return (u16_t)~(acc & 0xffffUL);
}

u16_t __real_ip_chksum_pseudo(struct pbuf *p, u8_t proto, u16_t proto_len,
                              const ip_addr_t *src, const ip_addr_t *dest);

static volatile int s_state;            /* 0 not checked, 1 fast path, -1 lwIP */
static uint32_t s_cycles_fast, s_cycles_lwip;
static const char *s_impl = "lwip";

#define FC_TEST_BYTES 1504

static void fc_one(struct pbuf *q, u8_t *payload, u16_t len, struct pbuf *next)
{
    memset(q, 0, sizeof *q);
    q->payload = payload;
    q->len = len;
    q->tot_len = len;
    q->next = next;
}

/* Compare the loop in s_halfwords with lwIP on random data: every start
 * alignment, every length up to 67 bytes and the usual packet sizes, single
 * pbufs and chains of three with odd and even parts, UDP and TCP. */
static bool fc_matches(u8_t *buf, const ip_addr_t *src, const ip_addr_t *dst)
{
    static const u16_t sizes[] = {68, 127, 128, 129, 255, 256, 511, 576, 1023, 1279, 1280, 1399, 1400, 1401, 1420, 1471, 1472, 1500};
    struct pbuf a, b, c;
    for (int off = 0; off < 4; off++) {
        for (int i = 0; i < 68 + (int)(sizeof sizes / sizeof sizes[0]); i++) {
            u16_t len = i < 68 ? (u16_t)i : sizes[i - 68];
            u8_t proto = (i & 1) ? IP_PROTO_TCP : IP_PROTO_UDP;
            fc_one(&a, buf + off, len, NULL);
            if (fc_pseudo_v4(&a, proto, len, ip_2_ip4(src), ip_2_ip4(dst))
                != __real_ip_chksum_pseudo(&a, proto, len, src, dst)) return false;
            if (len < 3) continue;
            /* three parts: lengths and starts from the random buffer */
            u16_t l1 = (u16_t)(1 + buf[(i + off) % FC_TEST_BYTES] % (len - 2));
            u16_t l2 = (u16_t)(1 + buf[(i * 7 + off) % FC_TEST_BYTES] % (len - l1 - 1));
            u16_t l3 = (u16_t)(len - l1 - l2);
            fc_one(&c, buf + off + l1 + l2, l3, NULL);
            fc_one(&b, buf + 1 + off + l1, l2, &c);     /* misaligned middle part */
            fc_one(&a, buf + off, l1, &b);
            a.tot_len = len;
            b.tot_len = (u16_t)(l2 + l3);
            if (fc_pseudo_v4(&a, proto, len, ip_2_ip4(src), ip_2_ip4(dst))
                != __real_ip_chksum_pseudo(&a, proto, len, src, dst)) return false;
        }
    }
    return true;
}

/* Fewest cycles of three runs over 1,400 bytes: the loop in s_halfwords
 * (lwip = false) or lwIP's own function. */
static uint32_t fc_cycles(u8_t *buf, const ip_addr_t *src, const ip_addr_t *dst, bool lwip)
{
    struct pbuf a;
    uint32_t best = UINT32_MAX;
    fc_one(&a, buf, 1400, NULL);
    for (int k = 0; k < 3; k++) {
        uint32_t t0 = esp_cpu_get_cycle_count();
        volatile u16_t x = lwip ? __real_ip_chksum_pseudo(&a, IP_PROTO_UDP, 1400, src, dst)
                                : fc_pseudo_v4(&a, IP_PROTO_UDP, 1400, ip_2_ip4(src), ip_2_ip4(dst));
        uint32_t t1 = esp_cpu_get_cycle_count();
        (void)x;
        if (t1 - t0 < best) best = t1 - t0;
    }
    return best;
}

/* Choose the loop: the vector unit (PIE) if it gives lwIP's results on this
 * chip, else the scalar loop if it does, else lwIP's own function. */
static int fc_check(void)
{
    u8_t *buf = heap_caps_malloc(FC_TEST_BYTES + 4, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!buf) buf = malloc(FC_TEST_BYTES + 4);
    if (!buf) return 0;                  /* try again on a later call */
    esp_fill_random(buf, FC_TEST_BYTES + 4);
    ip_addr_t src, dst;
    uint32_t r = esp_random();
    IP_ADDR4(&src, 100, 64 | (r & 0x3f), (r >> 8) & 0xff, (r >> 16) & 0xff);
    IP_ADDR4(&dst, 192, 168, (r >> 24) & 0xff, 7);
    static const struct { uint32_t (*fn)(const void *, uint32_t); const char *name; } loops[] = {
        {tsr_csum_halfwords_pie, "xtensa-pie"}, {tsr_csum_halfwords, "xtensa"}};
    int state = -1;
    for (unsigned k = 0; k < sizeof loops / sizeof loops[0]; k++) {
        s_halfwords = loops[k].fn;
        if (fc_matches(buf, &src, &dst)) {
            state = 1;
            s_impl = loops[k].name;
            break;
        }
        ESP_LOGW(TAG, "%s checksum loop differs from lwIP; not used", loops[k].name);
    }
    if (state > 0) {
        s_cycles_fast = fc_cycles(buf, &src, &dst, false);
        s_cycles_lwip = fc_cycles(buf, &src, &dst, true);
        ESP_LOGI(TAG, "%s checksum loop matches lwIP: %lu cycles for 1400 bytes (lwIP %lu)",
                 s_impl, (unsigned long)s_cycles_fast, (unsigned long)s_cycles_lwip);
    } else {
        s_halfwords = tsr_csum_halfwords;
        s_impl = "lwip";
    }
    free(buf);
    return state;
}

u16_t __wrap_ip_chksum_pseudo(struct pbuf *p, u8_t proto, u16_t proto_len,
                              const ip_addr_t *src, const ip_addr_t *dest)
{
    PH_BEGIN(t);
    int state = s_state;
    if (state == 0) {
        state = fc_check();
        s_state = state;
    }
    u16_t r;
#if LWIP_IPV6
    if (state <= 0 || IP_IS_V6(dest))
#else
    if (state <= 0)
#endif
        r = __real_ip_chksum_pseudo(p, proto, proto_len, src, dest);
    else
        r = fc_pseudo_v4(p, proto, proto_len, ip_2_ip4(src), ip_2_ip4(dest));
    PH_END(PH_CHKSUM_PSEUDO, t, proto_len);
    return r;
}

void fast_chksum_status(fast_chksum_status_t *out)
{
    if (!out) return;
    int state = s_state;
    out->checked = state != 0;
    out->active = state > 0;
    out->cycles_fast = s_cycles_fast;
    out->cycles_lwip = s_cycles_lwip;
    out->impl = state > 0 ? s_impl : "lwip";
}
