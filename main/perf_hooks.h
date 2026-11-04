#pragma once

/* Test-only cycle counters for the per-packet work of the TCP/IP task
 * ("-prof" images, TSR_PERF_PROFILE=1). In release images every macro is
 * empty and nothing is compiled. Cycles are those of the core that ran the
 * stage, preemption included; nested stages are inclusive. */

#include <stdint.h>

typedef enum {
    PH_IP4_INPUT,       /* __real_ip4_input: forwarding/local delivery, onward send included */
    PH_DNAT_PREP,       /* receive-DNAT preparation in __wrap_ip4_input */
    PH_ALLOW,           /* service-gateway filter in __wrap_ip4_input */
    PH_ROUTE_HOOK,      /* __wrap_ip4_route_src_hook */
    PH_NAPT_FWD,        /* __wrap_ip_napt_forward */
    PH_UDP_SENDTO,      /* udp_sendto (WireGuard and other UDP output) */
    PH_CHKSUM_PSEUDO,   /* ip_chksum_pseudo (UDP/TCP checksum) */
    PH_IP_CHKSUM,       /* inet_chksum (IPv4 header checksum) */
    PH_WIFI_TX,         /* esp_wifi_internal_tx_by_ref */
    PH_COUNT
} perf_hook_stage_t;

#if defined(TSR_PERF_PROFILE) && TSR_PERF_PROFILE
#include "esp_cpu.h"
#include "cJSON.h"
void perf_hooks_add(perf_hook_stage_t stage, uint32_t cycles, uint32_t bytes);
/* Adds {"stage": {"total","count","bytes","max"}} counters to `root`. */
void perf_hooks_report(cJSON *root);
#define PH_BEGIN(v) uint32_t v = esp_cpu_get_cycle_count()
#define PH_END(stage, v, bytes) perf_hooks_add((stage), esp_cpu_get_cycle_count() - (v), (uint32_t)(bytes))
#else
#define PH_BEGIN(v) ((void)0)
#define PH_END(stage, v, bytes) ((void)(bytes))
#endif
