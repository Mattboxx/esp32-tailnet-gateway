/* Test-only TCP/IP task counters: see perf_hooks.h. */
#include "perf_hooks.h"

#if defined(TSR_PERF_PROFILE) && TSR_PERF_PROFILE
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "lwip/udp.h"
#include "lwip/inet_chksum.h"
#include "esp_private/wifi.h"

typedef struct { uint64_t total, bytes; uint32_t count, max, migrated; } counter_t;
static counter_t s_c[PH_COUNT];
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static const char *const s_names[PH_COUNT] = {
    "ip4_input", "dnat_prep", "allow", "route_hook", "napt_forward",
    "udp_sendto", "chksum_pseudo", "ip_chksum", "wifi_tx",
};

void perf_hooks_end(perf_hook_stage_t stage, const ph_mark_t *mark, uint32_t bytes)
{
    uint32_t cycles = esp_cpu_get_cycle_count() - mark->cycles;
    /* Also discard a counter that went backwards (a CPU frequency change
     * rewrites CCOUNT): it reads as ~4e9 cycles and would swamp the average. */
    bool migrated = xPortGetCoreID() != mark->core || cycles > 0x80000000u;
    if ((unsigned)stage >= PH_COUNT) return;
    taskENTER_CRITICAL(&s_lock);
    counter_t *c = &s_c[stage];
    if (migrated) {
        c->migrated++;
    } else {
        c->total += cycles; c->bytes += bytes; c->count++;
        if (cycles > c->max) c->max = cycles;
    }
    taskEXIT_CRITICAL(&s_lock);
}

void perf_hooks_report(cJSON *root)
{
    counter_t copy[PH_COUNT];
    taskENTER_CRITICAL(&s_lock);
    for (int i = 0; i < PH_COUNT; i++) copy[i] = s_c[i];
    taskEXIT_CRITICAL(&s_lock);
    cJSON *o = cJSON_AddObjectToObject(root, "hook_profile");
    for (int i = 0; o && i < PH_COUNT; i++) {
        cJSON *s = cJSON_AddObjectToObject(o, s_names[i]);
        cJSON_AddNumberToObject(s, "total", (double)copy[i].total);
        cJSON_AddNumberToObject(s, "bytes", (double)copy[i].bytes);
        cJSON_AddNumberToObject(s, "count", copy[i].count);
        cJSON_AddNumberToObject(s, "max", copy[i].max);
        cJSON_AddNumberToObject(s, "migrated", copy[i].migrated);
    }
}

/* Link-time wraps (-Wl,--wrap, -prof images only; see main/CMakeLists.txt). */
err_t __real_udp_sendto(struct udp_pcb *pcb, struct pbuf *p, const ip_addr_t *dst_ip, u16_t dst_port);
err_t __wrap_udp_sendto(struct udp_pcb *pcb, struct pbuf *p, const ip_addr_t *dst_ip, u16_t dst_port)
{
    u16_t len = p ? p->tot_len : 0;
    PH_BEGIN(t);
    err_t e = __real_udp_sendto(pcb, p, dst_ip, dst_port);
    PH_END(PH_UDP_SENDTO, t, len);
    return e;
}

/* ip_chksum_pseudo is counted by its production wrapper (fast_chksum.c). */

u16_t __real_inet_chksum(const void *dataptr, u16_t len);
u16_t __wrap_inet_chksum(const void *dataptr, u16_t len)
{
    PH_BEGIN(t);
    u16_t r = __real_inet_chksum(dataptr, len);
    PH_END(PH_IP_CHKSUM, t, len);
    return r;
}

esp_err_t __real_esp_wifi_internal_tx_by_ref(wifi_interface_t ifx, void *buffer, size_t len, void *netstack_buf);
esp_err_t __wrap_esp_wifi_internal_tx_by_ref(wifi_interface_t ifx, void *buffer, size_t len, void *netstack_buf)
{
    PH_BEGIN(t);
    esp_err_t e = __real_esp_wifi_internal_tx_by_ref(ifx, buffer, len, netstack_buf);
    PH_END(PH_WIFI_TX, t, len);
    return e;
}
#endif
