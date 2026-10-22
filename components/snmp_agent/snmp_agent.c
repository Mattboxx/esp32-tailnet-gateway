/* Minimal SNMPv1/v2c read-only agent using BSD sockets.
 *
 * Runs as a FreeRTOS task listening on UDP 0.0.0.0:161.
 * Handles GET and GETNEXT.  No lwIP internal SNMP API required.
 *
 * OIDs supported:
 *   1.3.6.1.2.1.1.1.0          sysDescr
 *   1.3.6.1.2.1.1.3.0          sysUpTime (hundredths of seconds)
 *   1.3.6.1.2.1.1.4.0          sysContact
 *   1.3.6.1.2.1.1.5.0          sysName
 *   1.3.6.1.2.1.1.6.0          sysLocation
 *   1.3.6.1.2.1.1.7.0          sysServices = 79
 *
 *   1.3.6.1.2.1.2.1.0          ifNumber (3: eth0, wlan0, ts0)
 *   1.3.6.1.2.1.2.2.1.{1-8}.N  ifIndex/Descr/Type/Mtu/Speed/MAC/Admin/OperStatus
 *   1.3.6.1.2.1.2.2.1.{10,11}.N  ifInOctets / ifInUcastPkts   (live hooks)
 *   1.3.6.1.2.1.2.2.1.{16,17}.N  ifOutOctets / ifOutUcastPkts
 *                              N = 1 eth0, 2 wlan0, 3 ts0
 *
 * HOST-RESOURCES-MIB (RFC 2790):
 *   1.3.6.1.2.1.25.1.1.0       hrSystemUptime
 *   1.3.6.1.2.1.25.1.6.0       hrSystemProcesses (task count)
 *   1.3.6.1.2.1.25.2.2.0       hrMemorySize (KB of internal DRAM)
 *   1.3.6.1.2.1.25.2.3.1.*.N   hrStorageTable: 1 internal DRAM, 2 PSRAM
 *   1.3.6.1.2.1.25.3.2.1.*.N   hrDeviceTable: the two CPU cores
 *   1.3.6.1.2.1.25.3.3.1.2.N   hrProcessorLoad (0-100, 5-second window)
 *
 * ENTITY-MIB / ENTITY-SENSOR-MIB (RFC 6933 / 3433):
 *   1.3.6.1.2.1.47.1.1.1.1.*.1 entPhysicalTable: the temperature sensor
 *   1.3.6.1.2.1.99.1.1.1.*.1   entPhySensorTable: die temperature,
 *                              deci-degrees Celsius (precision 1)
 *
 * Private tree. 99999 is NOT an IANA-assigned enterprise number; it is
 * squatted. Everything else that used to live here now has a standard
 * home above, so only the one value with no standard equivalent remains:
 *   1.3.6.1.4.1.99999.1.1.4.0  heapMinFreeBytes (all-time low watermark)
 *   1.3.6.1.4.1.99999.2.N.0    Gauge32 operational metrics (snmp_operational.h);
 *                              N=1 is 0 until the firmware registers a
 *                              provider, and then every other value is 0 too.
 *
 * SPDX-License-Identifier: MIT
 */
#include "snmp_agent.h"
#include "snmp_operational.h"
#include "nvs.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "esp_app_desc.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "driver/temperature_sensor.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#include "lwip/ip4_addr.h"
#include "lwip/tcpip.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <errno.h>

#define TAG          "snmp_agent"
#define SNMP_PORT    161
#define PKT_BUF     2048
#define TASK_STACK  4096
#define MAX_OID     16
#define MAX_TASKS    52   /* enough for a busy ESP-IDF system */
#define CPU_SAMPLE_S  5   /* CPU usage sampling interval (seconds) */
#define VBL_BUF      2000
#define PDU_BODY_BUF 2048
#define VB_BUF        320   /* OID + BER header + 255-byte configured string */
#define COMM_TLV_BUF  260

/* ------------------------------------------------------------------ */
/* Shared mutable state (protected by s_mutex)                        */
/* ------------------------------------------------------------------ */
static SemaphoreHandle_t  s_mutex;
/* The web form must retain these while SNMP is disabled, so unlike the
 * task work buffers they live for the process lifetime. Keep them in PSRAM
 * nevertheless: users who never enable SNMP must not lose internal heap. */
typedef struct {
    char community[256];
    char sysname[256];
    char syscontact[256];
    char syslocation[256];
    char sysdescr[128];
} snmp_strings_t;
static snmp_strings_t *s_strings;

#define SNMP_CONFIG_MAGIC 0x534e4d31U  /* SNM1 */
typedef struct {
    uint32_t magic;
    uint8_t enabled;
    uint8_t reserved[3];
    char community[256];
    char sysname[256];
    char syscontact[256];
    char syslocation[256];
} snmp_persist_t;
static bool   s_enabled  = false;
static bool   s_running  = false;
static bool   s_starting = false;
static bool   s_stopping = false;
static int    s_sock     = -1;

/* These are deliberately task-owned: keeping them static would charge every
 * router roughly 8.5 KB of scarce internal RAM even when SNMP is disabled.
 * The task allocates this one block from PSRAM only while it is running and
 * frees it before it exits. */
typedef struct {
    uint8_t rx[PKT_BUF];
    uint8_t tx[PKT_BUF];
    uint8_t vbl_buf[VBL_BUF];
    uint8_t pdu_body[PDU_BODY_BUF];
    uint8_t vb[VB_BUF];
    uint8_t comm_tlv[COMM_TLV_BUF];
} snmp_buffers_t;

/* ------------------------------------------------------------------ */
/* Hardware / telemetry state (read-only after init, no mutex needed) */
/* ------------------------------------------------------------------ */
static temperature_sensor_handle_t s_temp_sensor = NULL;

/* Per-interface traffic counters — updated from the lwIP task, read from the
 * SNMP task. 32-bit aligned writes are atomic on Xtensa; no mutex needed.
 *
 * There is no other way to get these numbers in this build: netif->mib2_counters
 * is compiled out (MIB2_STATS defaults to 0 in lwip/opt.h and only LWIP_SNMP
 * turns it on, which ESP-IDF 5.5.3 exposes no Kconfig for). So we wrap the
 * netif function pointers and count pbufs as they go past.                   */
typedef struct {
    volatile uint32_t rx_octets, rx_pkts, tx_octets, tx_pkts;
    /* Originals, saved before wrapping. */
    netif_input_fn      orig_input;
    netif_linkoutput_fn orig_linkoutput;  /* L2 netifs (eth0, wlan0) */
    netif_output_fn     orig_output;      /* L3 netifs (ts0 tunnel)  */
} iftraf_t;

/* Slots are indexed by SNMP ifIndex - 1: 0=eth0, 1=wlan0, 2=ts0. */
#define IF_ETH   0
#define IF_WIFI  1
#define IF_TS    2
#define IF_SLOTS 3

static iftraf_t s_traf[IF_SLOTS];
static atomic_bool s_hooks_enabled = false;

/* CPU usage (0-100%), updated every CPU_SAMPLE_S seconds. */
static volatile uint32_t s_cpu0_usage = 0;
static volatile uint32_t s_cpu1_usage = 0;
static esp_timer_handle_t s_cpu_timer  = NULL;
/* Set only by install_traffic_hooks_cb() in the TCP/IP thread. */
static volatile bool s_ts_up = false;

/* Sampling state for CPU (lives only in the timer callback). */
static uint32_t s_prev_idle0_us   = 0;
static uint32_t s_prev_idle1_us   = 0;
static uint64_t s_prev_wall_us    = 0;

/* MAC cache for eth0 and wlan0. Latched independently: a build with no
 * Ethernet never resolves ETH_DEF, and a shared flag would keep the wlan0
 * MAC re-reading on every query for the rest of the uptime. */
static uint8_t s_eth_mac[6];
static uint8_t s_wifi_mac[6];
static bool    s_eth_mac_fetched  = false;
static bool    s_wifi_mac_fetched = false;

/* ------------------------------------------------------------------ */
/* Traffic hooks                                                       */
/* ------------------------------------------------------------------ */
/* Function pointers carry no context, so each slot needs its own trio of
 * shims. The bodies are identical bar the slot index — generate them.  */
#define DEFINE_IF_HOOKS(slot, pfx)                                            \
    static err_t pfx##_input_hook(struct pbuf *p, struct netif *n)            \
    {                                                                         \
        s_traf[slot].rx_octets += p->tot_len;                                 \
        s_traf[slot].rx_pkts++;                                               \
        return s_traf[slot].orig_input(p, n);                                 \
    }                                                                         \
    static err_t pfx##_linkoutput_hook(struct netif *n, struct pbuf *p)       \
    {                                                                         \
        s_traf[slot].tx_octets += p->tot_len;                                 \
        s_traf[slot].tx_pkts++;                                               \
        return s_traf[slot].orig_linkoutput(n, p);                            \
    }                                                                         \
    static err_t pfx##_output_hook(struct netif *n, struct pbuf *p,           \
                                   const ip4_addr_t *ipaddr)                  \
    {                                                                         \
        s_traf[slot].tx_octets += p->tot_len;                                 \
        s_traf[slot].tx_pkts++;                                               \
        return s_traf[slot].orig_output(n, p, ipaddr);                        \
    }

DEFINE_IF_HOOKS(IF_ETH,  eth)
DEFINE_IF_HOOKS(IF_WIFI, wifi)
DEFINE_IF_HOOKS(IF_TS,   ts)

typedef struct {
    netif_input_fn      input;
    netif_linkoutput_fn linkoutput;
    netif_output_fn     output;
} if_hookset_t;

static const if_hookset_t s_hookset[IF_SLOTS] = {
    [IF_ETH]  = { eth_input_hook,  eth_linkoutput_hook,  eth_output_hook  },
    [IF_WIFI] = { wifi_input_hook, wifi_linkoutput_hook, wifi_output_hook },
    [IF_TS]   = { ts_input_hook,   ts_linkoutput_hook,   ts_output_hook   },
};

/* Wrap one netif's pointers, saving the originals first.
 *
 * Hooking an already-hooked netif is a no-op, so this is safe to call
 * repeatedly — which is the point: netifs appear long after snmp_agent_init()
 * runs, and ts0 in particular comes and goes with the tunnel. If a netif is
 * torn down and rebuilt, its pointers are fresh and we re-wrap them.
 *
 * TX is counted at exactly one layer: L2 netifs (eth0, wlan0) carry both
 * ->output (etharp_output) and ->linkoutput (driver TX) and the former calls
 * the latter, so hooking linkoutput alone avoids double counting. The
 * WireGuard netif is an L3 tunnel with linkoutput == NULL, so there we take
 * ->output instead.
 *
 * Racing the lwIP task is benign: each install is a single aligned pointer
 * store, and the original is saved before the swap, so a packet in flight
 * either misses the count or takes the new path — never a torn pointer.   */
static void hook_netif(int slot, struct netif *n)
{
    if (!n) return;
    const if_hookset_t *h = &s_hookset[slot];
    bool fresh = false;

    if (n->input && n->input != h->input) {
        s_traf[slot].orig_input = n->input;
        n->input = h->input;
        fresh = true;
    }
    if (n->linkoutput) {
        if (n->linkoutput != h->linkoutput) {
            s_traf[slot].orig_linkoutput = n->linkoutput;
            n->linkoutput = h->linkoutput;
            fresh = true;
        }
    } else if (n->output && n->output != h->output) {
        s_traf[slot].orig_output = n->output;
        n->output = h->output;
        fresh = true;
    }

    if (fresh)
        ESP_LOGI(TAG, "traffic hooks installed on ifIndex %d (%c%c%u)",
                 slot + 1, n->name[0], n->name[1], n->num);
}

/* Restore only pointers we still own. This runs in the TCP/IP thread, like
 * installation, after the periodic timer has been stopped. */
static void unhook_netif(int slot, struct netif *n)
{
    if (!n) return;
    const if_hookset_t *h = &s_hookset[slot];
    if (n->input == h->input) n->input = s_traf[slot].orig_input;
    if (n->linkoutput == h->linkoutput)
        n->linkoutput = s_traf[slot].orig_linkoutput;
    if (n->output == h->output) n->output = s_traf[slot].orig_output;
}

/* Re-scan for interfaces worth counting. Called when the agent starts and
 * then from the telemetry tick, so rebuilt tunnel netifs are covered. */
static struct netif *find_ts_netif(void);

/* Runs in the lwIP TCP/IP thread — see install_traffic_hooks(). */
static void install_traffic_hooks_cb(void *ctx)
{
    (void)ctx;
    if (!atomic_load(&s_hooks_enabled)) return;
    esp_netif_t *e = esp_netif_get_handle_from_ifkey("ETH_DEF");
    if (e) hook_netif(IF_ETH, (struct netif *)esp_netif_get_netif_impl(e));

    esp_netif_t *w = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (w) hook_netif(IF_WIFI, (struct netif *)esp_netif_get_netif_impl(w));

    struct netif *ts = find_ts_netif();
    hook_netif(IF_TS, ts);
    s_ts_up = ts && netif_is_up(ts);
}

static void uninstall_traffic_hooks_cb(void *ctx)
{
    esp_netif_t *e = esp_netif_get_handle_from_ifkey("ETH_DEF");
    if (e) unhook_netif(IF_ETH, (struct netif *)esp_netif_get_netif_impl(e));
    esp_netif_t *w = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (w) unhook_netif(IF_WIFI, (struct netif *)esp_netif_get_netif_impl(w));
    unhook_netif(IF_TS, find_ts_netif());
    xTaskNotifyGive((TaskHandle_t)ctx);
}

/* netif_list and the netif function pointers belong to the lwIP thread, and
 * CONFIG_LWIP_TCPIP_CORE_LOCKING is off in this build — so walking the list
 * and swapping pointers from the telemetry timer was a race: the tunnel netif
 * can be removed and freed between find_ts_netif() returning it and the hook
 * being written into it, which is a write to freed memory on a reconnect that
 * lands in that window. Run the whole scan inside the TCP/IP thread instead,
 * the same idiom microlink uses for its own netif bring-up.
 *
 * Non-blocking on purpose: this is called from an esp_timer callback, which
 * must not block. If the mailbox is full the install is simply skipped and
 * the next tick retries — hook_netif() is idempotent, so nothing is lost but
 * five seconds of counting on an interface that just appeared. */
static void install_traffic_hooks(void)
{
    tcpip_callback_with_block(install_traffic_hooks_cb, NULL, 0);
}

static void uninstall_traffic_hooks(void)
{
    /* The block argument waits only for mailbox space, not callback
     * completion. Wait for the TCP/IP thread to finish restoring pointers
     * before another SNMP task can start. */
    if (tcpip_callback_with_block(uninstall_traffic_hooks_cb,
                                  xTaskGetCurrentTaskHandle(), 1) == ERR_OK)
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    else
        ESP_LOGE(TAG, "failed to remove traffic hooks");
}

/* ------------------------------------------------------------------ */
/* Telemetry tick (5-second periodic timer)                           */
/* ------------------------------------------------------------------ */
/* Samples CPU usage and re-arms traffic hooks when the tunnel netif is
 * rebuilt after a reconnect. */
static void telemetry_tick_cb(void *arg)
{
    install_traffic_hooks();

    /* A static snapshot costs about 2 KB of internal DRAM permanently. The
     * timer only exists while SNMP is running, so take a short-lived PSRAM
     * snapshot instead. */
    TaskStatus_t *tasks = heap_caps_malloc(sizeof(*tasks) * MAX_TASKS,
                                           MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!tasks) {
        ESP_LOGW(TAG, "CPU sample skipped: no PSRAM");
        return;
    }
    uint32_t total_us = 0;   /* wall-time snapshot (≈ esp_timer_get_time) */
    UBaseType_t n = uxTaskGetSystemState(tasks, MAX_TASKS, &total_us);

    /* uxTaskGetSystemState returns 0 if MAX_TASKS is too small to hold the
     * whole system. Bail rather than treat an empty array as "no idle
     * time", which would report a permanent 100%. */
    if (n == 0) { heap_caps_free(tasks); return; }

    uint32_t idle0_us = 0, idle1_us = 0;
    bool found0 = false, found1 = false;
    for (UBaseType_t i = 0; i < n; i++) {
        const char *nm = tasks[i].pcTaskName;
        /* SMP idle task names: "IDLE0" (core 0), "IDLE1" (core 1). */
        if (nm[0]=='I' && nm[1]=='D' && nm[2]=='L' && nm[3]=='E') {
            if (nm[4] == '1') { idle1_us = tasks[i].ulRunTimeCounter; found1 = true; }
            else              { idle0_us = tasks[i].ulRunTimeCounter; found0 = true; }
        }
    }
    if (!found0) {                /* names changed under us — keep last values */
        heap_caps_free(tasks);
        return;
    }

    uint64_t wall_us = (uint64_t)esp_timer_get_time();
    uint64_t dw = wall_us - s_prev_wall_us;
    uint32_t di0 = idle0_us - s_prev_idle0_us;
    uint32_t di1 = idle1_us - s_prev_idle1_us;

    s_prev_idle0_us = idle0_us;
    s_prev_idle1_us = idle1_us;
    s_prev_wall_us  = wall_us;

    /* usage% = 100 - (idle_delta / wall_delta) * 100. Both are esp_timer
     * microseconds, so they are directly comparable. Clamp when a core was
     * idle for the whole window (idle_delta can edge past wall_delta because
     * the two are not sampled at the same instant). */
    if (dw > 0) {
        s_cpu0_usage = (di0 >= dw) ? 0 : (uint32_t)(100 - (uint64_t)di0 * 100 / dw);
        s_cpu1_usage = !found1 ? 0
                     : (di1 >= dw) ? 0 : (uint32_t)(100 - (uint64_t)di1 * 100 / dw);
    }
    (void)total_us;
    heap_caps_free(tasks);
}

/* ------------------------------------------------------------------ */
/* Tailscale netif lookup                                              */
/* ------------------------------------------------------------------ */
static struct netif *find_ts_netif(void)
{
    for (struct netif *n = netif_list; n; n = n->next) {
        /* A WiFi or Ethernet uplink may also receive a CGNAT address.
         * Hooking it as both the uplink and ts0 makes the wrappers call
         * each other recursively on the next scan. WireGuard names its
         * actual tunnel netif "wg". */
        if (n->name[0] == 'w' && n->name[1] == 'g') return n;
    }
    return NULL;
}

/* ------------------------------------------------------------------ */
/* MAC cache                                                           */
/* ------------------------------------------------------------------ */
static void ensure_macs(void)
{
    /* Latch each side only once its address is real, so a query that arrives
     * before the interfaces are up doesn't cache 00:00:00:00:00:00 for the
     * rest of the uptime. An interface the build doesn't have simply never
     * latches and keeps reporting the all-zero address, which is what
     * ifPhysAddress should say for an interface that isn't there. */
    if (!s_eth_mac_fetched) {
        esp_netif_t *eth = esp_netif_get_handle_from_ifkey("ETH_DEF");
        if (eth) s_eth_mac_fetched = (esp_netif_get_mac(eth, s_eth_mac) == ESP_OK);
    }
    if (!s_wifi_mac_fetched) {
        esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        if (sta) s_wifi_mac_fetched = (esp_netif_get_mac(sta, s_wifi_mac) == ESP_OK);
    }
}

/* ------------------------------------------------------------------ */
/* BER codec helpers                                                   */
/* ------------------------------------------------------------------ */

static int ber_put_len(uint8_t *b, int cap, int len)
{
    if (len < 0x80) {
        if (cap < 1) return 0;
        b[0] = (uint8_t)len; return 1;
    }
    if (len <= 0xff) {
        if (cap < 2) return 0;
        b[0] = 0x81; b[1] = (uint8_t)len; return 2;
    }
    if (cap < 3) return 0;
    b[0] = 0x82; b[1] = (len >> 8) & 0xff; b[2] = len & 0xff; return 3;
}

static int ber_get_len(const uint8_t *b, int avail, int *out)
{
    if (avail < 1) return -1;
    if (b[0] < 0x80) { *out = b[0]; return 1; }
    if (b[0] == 0x81) { if (avail < 2) return -1; *out = b[1]; return 2; }
    if (b[0] == 0x82) { if (avail < 3) return -1; *out = (b[1]<<8)|b[2]; return 3; }
    return -1;
}

/* tag supplied: 0x41=Counter32, 0x42=Gauge32, 0x43=TimeTicks */
static int ber_enc_u32(uint8_t *b, int cap, uint8_t tag, uint32_t v)
{
    uint8_t vb[5]; int vn = 0;
    if (v > 0xffffff)  vb[vn++] = (v >> 24) & 0xff;
    if (v > 0xffff)    vb[vn++] = (v >> 16) & 0xff;
    if (v > 0xff)      vb[vn++] = (v >>  8) & 0xff;
    vb[vn++] = v & 0xff;
    if (vb[0] & 0x80) { memmove(vb+1, vb, vn); vb[0] = 0; vn++; }
    int llen = ber_put_len(b+1, cap-1, vn);
    if (!llen) return 0;
    int tot = 1 + llen + vn;
    if (cap < tot) return 0;
    b[0] = tag;
    memcpy(b + 1 + llen, vb, vn);
    return tot;
}

static int ber_enc_i32(uint8_t *b, int cap, int32_t v)
{
    uint8_t vb[4];
    vb[0] = (v >> 24) & 0xff; vb[1] = (v >> 16) & 0xff;
    vb[2] = (v >>  8) & 0xff; vb[3] =  v        & 0xff;
    int s = 0;
    while (s < 3 && vb[s] == (vb[s+1] & 0x80 ? 0xff : 0x00)
           && (vb[s] & 0x80) == (vb[s+1] & 0x80))
        s++;
    int vn = 4 - s;
    int llen = ber_put_len(b+1, cap-1, vn);
    if (!llen) return 0;
    int tot = 1 + llen + vn;
    if (cap < tot) return 0;
    b[0] = 0x02;
    memcpy(b + 1 + llen, vb + s, vn);
    return tot;
}

/* strnlen, not strlen: s comes from a getter in s_mib[] and nothing here can
 * prove it is terminated. Anything longer than the buffer cannot be encoded
 * anyway, so stopping the scan at cap loses nothing and keeps the length out
 * of the range where 1 + llen + slen overflows int. The remaining-space test
 * is then written against cap rather than against that sum. */
static int ber_enc_str(uint8_t *b, int cap, const char *s)
{
    if (cap < 2) return 0;
    int slen = (int)strnlen(s, (size_t)cap);
    int llen = ber_put_len(b+1, cap-1, slen);
    if (!llen) return 0;
    if (slen > cap - 1 - llen) return 0;
    b[0] = 0x04;
    memcpy(b + 1 + llen, s, slen);
    return 1 + llen + slen;
}

static int ber_enc_octstr(uint8_t *b, int cap, const uint8_t *bytes, int n)
{
    int llen = ber_put_len(b+1, cap-1, n);
    if (!llen) return 0;
    int tot = 1 + llen + n;
    if (cap < tot) return 0;
    b[0] = 0x04;
    memcpy(b + 1 + llen, bytes, n);
    return tot;
}

static int ber_enc_oid(uint8_t *b, int cap, const uint32_t *arc, int n)
{
    if (n < 2) return 0;
    uint8_t tmp[128]; int tlen = 0;
    tmp[tlen++] = (uint8_t)(40 * arc[0] + arc[1]);
    for (int i = 2; i < n; i++) {
        uint32_t v = arc[i];
        if (v < 0x80) { tmp[tlen++] = (uint8_t)v; continue; }
        uint8_t sub[5]; int sn = 0;
        while (v) { sub[sn++] = (uint8_t)(v & 0x7f); v >>= 7; }
        for (int j = sn - 1; j >= 0; j--)
            tmp[tlen++] = sub[j] | (j > 0 ? 0x80 : 0);
    }
    int llen = ber_put_len(b+1, cap-1, tlen);
    if (!llen) return 0;
    int tot = 1 + llen + tlen;
    if (cap < tot) return 0;
    b[0] = 0x06;
    memcpy(b + 1 + llen, tmp, tlen);
    return tot;
}

static int ber_dec_oid(const uint8_t *b, int len, uint32_t *arc, int *n_out, int maxn)
{
    if (len == 0 || maxn < 2) return 0;
    int n = 0;
    arc[n++] = b[0] / 40;
    arc[n++] = b[0] % 40;
    for (int i = 1; i < len; ) {
        uint32_t v = 0;
        do {
            if (i >= len || v > (UINT32_MAX >> 7)) return 0;
            v = (v << 7) | (b[i] & 0x7f);
        } while (b[i++] & 0x80);
        if (n >= maxn) return 0;
        arc[n++] = v;
    }
    *n_out = n; return 1;
}

/* Read one TLV header and validate that its content really is present.
 *
 * Every length in an SNMP datagram is attacker-supplied, so a raw
 * ber_get_len() result must never be used to index or copy: a two-byte
 * length can claim 65535 bytes of content that the 2 KB receive buffer does
 * not have. This wrapper rejects any TLV whose body runs past the end of
 * the bytes we actually received.
 *
 * On success advances *pp past the header, shrinks *rem accordingly, stores
 * the content length in *len and returns the tag. Returns -1 on any
 * malformed or over-long header. Callers still advance past the content
 * themselves, since some need to look at it first.                       */
static int ber_tlv(const uint8_t **pp, int *rem, int *len)
{
    const uint8_t *p = *pp;
    if (*rem < 2) return -1;
    int l, ls = ber_get_len(p + 1, *rem - 1, &l);
    if (ls < 0 || l < 0) return -1;
    if (l > *rem - 1 - ls) return -1;      /* body runs past the datagram */
    *pp   = p + 1 + ls;
    *rem -= 1 + ls;
    *len  = l;
    return p[0];
}

static int seq_hdr(uint8_t *hdr, int cap, uint8_t tag, int inner_len)
{
    hdr[0] = tag;
    int ll = ber_put_len(hdr+1, cap-1, inner_len);
    return ll ? 1 + ll : 0;
}

/* ------------------------------------------------------------------ */
/* OID table (lexicographic order)                                    */
/* ------------------------------------------------------------------ */
typedef struct { uint32_t arc[MAX_OID]; int n; } oid_t;

typedef enum {
    VT_STRING, VT_INT32, VT_UINT32, VT_TIMETICKS,
    VT_GAUGE32, VT_COUNTER32, VT_PHYS_ADDR, VT_OID
} vtype_t;

typedef union { const char *s; int32_t i; uint32_t u; const oid_t *o; } val_t;
typedef val_t (*getter_fn)(void);
typedef struct { oid_t oid; vtype_t vt; getter_fn get; } mib_row_t;

/* --- system group --- */
static val_t g_sysdescr(void)    { return (val_t){ .s = s_strings ? s_strings->sysdescr : "" }; }
static val_t g_sysuptime(void)   { return (val_t){ .u = (uint32_t)(esp_timer_get_time() / 10000ULL) }; }
static val_t g_syscontact(void)  { return (val_t){ .s = s_strings ? s_strings->syscontact : "" }; }
static val_t g_sysname(void)     { return (val_t){ .s = s_strings ? s_strings->sysname : "" }; }
static val_t g_syslocation(void) { return (val_t){ .s = s_strings ? s_strings->syslocation : "" }; }
static val_t g_sysservices(void) { return (val_t){ .i = 79 }; }

/* --- ifTable scalars --- */
static val_t g_ifnumber(void) { return (val_t){ .i = 3 }; }

/* ifIndex */
static val_t g_eth_ifindex(void)  { return (val_t){ .i = 1 }; }
static val_t g_wifi_ifindex(void) { return (val_t){ .i = 2 }; }
static val_t g_ts_ifindex(void)   { return (val_t){ .i = 3 }; }

/* ifDescr */
static val_t g_eth_ifdescr(void)  { return (val_t){ .s = "eth0" }; }
static val_t g_wifi_ifdescr(void) { return (val_t){ .s = "wlan0" }; }
static val_t g_ts_ifdescr(void)   { return (val_t){ .s = "ts0" }; }

/* ifType: 6=ethernetCsmacd, 71=ieee80211, 131=tunnel */
static val_t g_eth_iftype(void)  { return (val_t){ .i = 6 }; }
static val_t g_wifi_iftype(void) { return (val_t){ .i = 71 }; }
static val_t g_ts_iftype(void)   { return (val_t){ .i = 131 }; }

/* ifMtu */
static val_t g_eth_ifmtu(void)  { return (val_t){ .i = 1500 }; }
static val_t g_wifi_ifmtu(void) { return (val_t){ .i = 1500 }; }
static val_t g_ts_ifmtu(void)   { return (val_t){ .i = 1280 }; }

/* ifSpeed (bps) */
static val_t g_eth_ifspeed(void)  { return (val_t){ .u = 100000000U }; }
static val_t g_wifi_ifspeed(void) { return (val_t){ .u =  54000000U }; }
static val_t g_ts_ifspeed(void)   { return (val_t){ .u =          0U }; }

/* ifPhysAddress */
static val_t g_eth_ifphysaddr(void)  { ensure_macs(); return (val_t){ .s = (const char*)s_eth_mac }; }
static val_t g_wifi_ifphysaddr(void) { ensure_macs(); return (val_t){ .s = (const char*)s_wifi_mac }; }
static val_t g_ts_ifphysaddr(void)   { return (val_t){ .s = "" }; } /* tunnel: no MAC */

/* ifAdminStatus (1=up) */
static val_t g_eth_ifadminstatus(void)  { return (val_t){ .i = 1 }; }
static val_t g_wifi_ifadminstatus(void) { return (val_t){ .i = 1 }; }
static val_t g_ts_ifadminstatus(void)   { return (val_t){ .i = 1 }; }

/* ifOperStatus (1=up, 2=down) */
static val_t g_eth_ifoperstatus(void)
{
    esp_netif_t *e = esp_netif_get_handle_from_ifkey("ETH_DEF");
    return (val_t){ .i = (e && esp_netif_is_netif_up(e)) ? 1 : 2 };
}
static val_t g_wifi_ifoperstatus(void)
{
    esp_netif_t *s = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    return (val_t){ .i = (s && esp_netif_is_netif_up(s)) ? 1 : 2 };
}
static val_t g_ts_ifoperstatus(void)
{
    /* The SNMP task must not walk netif_list: it belongs to the TCP/IP
     * thread and ts0 can be rebuilt underneath a reconnect. */
    return (val_t){ .i = s_ts_up ? 1 : 2 };
}

/* ifInOctets / ifInUcastPkts / ifOutOctets / ifOutUcastPkts, per interface */
static val_t g_eth_rx_octets(void)  { return (val_t){ .u = s_traf[IF_ETH].rx_octets };  }
static val_t g_eth_rx_pkts(void)    { return (val_t){ .u = s_traf[IF_ETH].rx_pkts };    }
static val_t g_eth_tx_octets(void)  { return (val_t){ .u = s_traf[IF_ETH].tx_octets };  }
static val_t g_eth_tx_pkts(void)    { return (val_t){ .u = s_traf[IF_ETH].tx_pkts };    }
static val_t g_wifi_rx_octets(void) { return (val_t){ .u = s_traf[IF_WIFI].rx_octets }; }
static val_t g_wifi_rx_pkts(void)   { return (val_t){ .u = s_traf[IF_WIFI].rx_pkts };   }
static val_t g_wifi_tx_octets(void) { return (val_t){ .u = s_traf[IF_WIFI].tx_octets }; }
static val_t g_wifi_tx_pkts(void)   { return (val_t){ .u = s_traf[IF_WIFI].tx_pkts };   }
static val_t g_ts_rx_octets(void)   { return (val_t){ .u = s_traf[IF_TS].rx_octets };   }
static val_t g_ts_rx_pkts(void)     { return (val_t){ .u = s_traf[IF_TS].rx_pkts };     }
static val_t g_ts_tx_octets(void)   { return (val_t){ .u = s_traf[IF_TS].tx_octets };   }
static val_t g_ts_tx_pkts(void)     { return (val_t){ .u = s_traf[IF_TS].tx_pkts };     }

/* --- private tree --- */
/* The only heap figure with no standard equivalent: hrStorageTable reports
 * current size and usage, but has no all-time-low watermark column. */
static val_t g_heap_minfree(void) { return (val_t){ .u = (uint32_t)esp_get_minimum_free_heap_size() }; }

/* --- shared by entPhySensorValue --- */
bool snmp_agent_chip_temp_c(float *out_c)
{
    if (!s_temp_sensor || !out_c) return false;
    float c = 0.0f;
    if (temperature_sensor_get_celsius(s_temp_sensor, &c) != ESP_OK) return false;
    *out_c = c;
    return true;
}

static val_t g_temperature(void)
{
    float c = 0.0f;
    if (!snmp_agent_chip_temp_c(&c)) return (val_t){ .i = -9999 };
    return (val_t){ .i = (int32_t)(c * 10.0f) };
}

/* --- HOST-RESOURCES-MIB (RFC 2790) --- */
/* This is where standard NMS software (LibreNMS, Observium, Zabbix, PRTG,
 * Cacti) looks for CPU load and memory, so expose it here rather than
 * relying on the private tree.                                            */
static val_t g_hr_uptime(void)    { return g_sysuptime(); }
static val_t g_hr_processes(void) { return (val_t){ .u = (uint32_t)uxTaskGetNumberOfTasks() }; }
static val_t g_hr_mem_size(void)
{
    /* hrMemorySize is "the amount of physical read-write main memory",
     * in KBytes. Report the internal DRAM heap the allocator manages. */
    return (val_t){ .i = (int32_t)(heap_caps_get_total_size(MALLOC_CAP_INTERNAL) / 1024) };
}

/* hrDeviceTable rows for the two cores, so processors are discoverable and
 * not just readable. hrDeviceType points at hrDeviceProcessor.            */
static const oid_t s_oid_hr_processor = {{1,3,6,1,2,1,25,3,1,3}, 10};
static const oid_t s_oid_zero         = {{0,0}, 2};

static val_t g_hr_dev_index0(void) { return (val_t){ .i = 1 }; }
static val_t g_hr_dev_index1(void) { return (val_t){ .i = 2 }; }
static val_t g_hr_dev_type(void)   { return (val_t){ .o = &s_oid_hr_processor }; }
static val_t g_hr_dev_descr0(void) { return (val_t){ .s = "CPU core 0 (Xtensa LX7)" }; }
static val_t g_hr_dev_descr1(void) { return (val_t){ .s = "CPU core 1 (Xtensa LX7)" }; }
static val_t g_hr_frwid(void)      { return (val_t){ .o = &s_oid_zero }; }

/* hrProcessorLoad: INTEGER (0..100), per-core utilisation. */
static val_t g_hr_cpu0_load(void) { return (val_t){ .i = (int32_t)s_cpu0_usage }; }
static val_t g_hr_cpu1_load(void) { return (val_t){ .i = (int32_t)s_cpu1_usage }; }

/* hrStorageTable: 1 = internal DRAM, 2 = PSRAM. Allocation unit is one
 * byte, so Size and Used are plain byte counts. This is the table NMS
 * software graphs as "memory", which the private heap OIDs never were. */
static const oid_t s_oid_hr_ram = {{1,3,6,1,2,1,25,2,1,2}, 10};   /* hrStorageRam */

static val_t g_hrs_index1(void) { return (val_t){ .i = 1 }; }
static val_t g_hrs_index2(void) { return (val_t){ .i = 2 }; }
static val_t g_hrs_type(void)   { return (val_t){ .o = &s_oid_hr_ram }; }
static val_t g_hrs_descr1(void) { return (val_t){ .s = "Internal DRAM" }; }
static val_t g_hrs_descr2(void) { return (val_t){ .s = "PSRAM" }; }
static val_t g_hrs_units(void)  { return (val_t){ .i = 1 }; }

static int32_t heap_total(uint32_t caps) { return (int32_t)heap_caps_get_total_size(caps); }
static int32_t heap_used(uint32_t caps)
{
    size_t tot = heap_caps_get_total_size(caps);
    size_t fre = heap_caps_get_free_size(caps);
    return (int32_t)(tot > fre ? tot - fre : 0);
}
static val_t g_hrs_size1(void) { return (val_t){ .i = heap_total(MALLOC_CAP_INTERNAL) }; }
static val_t g_hrs_size2(void) { return (val_t){ .i = heap_total(MALLOC_CAP_SPIRAM) }; }
static val_t g_hrs_used1(void) { return (val_t){ .i = heap_used(MALLOC_CAP_INTERNAL) }; }
static val_t g_hrs_used2(void) { return (val_t){ .i = heap_used(MALLOC_CAP_SPIRAM) }; }

/* --- ENTITY-MIB / ENTITY-SENSOR-MIB (RFC 6933 / 3433) --- */
/* The standard home for the die temperature. entPhySensorTable rows are
 * keyed by an entPhysicalIndex, so entity 1 below exists to give the
 * sensor something to hang off — without it, discovery finds nothing. */
static val_t g_ent_descr(void)     { return (val_t){ .s = "ESP32-S3 on-die temperature sensor" }; }
static val_t g_ent_contained(void) { return (val_t){ .i = 0 }; }
static val_t g_ent_class(void)     { return (val_t){ .i = 8 }; }  /* sensor(8) */
static val_t g_ent_relpos(void)    { return (val_t){ .i = -1 }; }
static val_t g_ent_name(void)      { return (val_t){ .s = "chipTemp" }; }

/* entPhySensorValue is scaled by entPhySensorPrecision decimal places, so
 * precision 1 means the value is deci-degrees — exactly what the private
 * chipTemp OID already reported, now self-describing. */
static val_t g_ents_type(void)   { return (val_t){ .i = 8 }; }  /* celsius(8) */
static val_t g_ents_scale(void)  { return (val_t){ .i = 9 }; }  /* units(9)   */
static val_t g_ents_prec(void)   { return (val_t){ .i = 1 }; }
static val_t g_ents_value(void)  { return g_temperature(); }
static val_t g_ents_status(void) { return (val_t){ .i = s_temp_sensor ? 1 : 2 }; } /* ok / unavailable */
static val_t g_ents_units(void)  { return (val_t){ .s = "C" }; }
static val_t g_ents_ts(void)     { return g_sysuptime(); }
static val_t g_ents_rate(void)   { return (val_t){ .i = 0 }; }  /* read on demand */

/* --- operational snapshot (begin) --- */
/* One provider call per second at most, from the agent task only; a burst
 * of GETNEXT walks never multiplies the cost of collecting the snapshot. */
static _Atomic(snmp_operational_provider_t) s_ops_provider;
static snmp_operational_metrics_t s_ops;
static int64_t s_ops_at_us;
static bool    s_ops_valid;

void snmp_agent_set_operational_provider(snmp_operational_provider_t provider)
{
    atomic_store(&s_ops_provider, provider);
}

static uint32_t ops_metric(unsigned id)
{
    int64_t now = esp_timer_get_time();
    if (!s_ops_valid || now < s_ops_at_us || now - s_ops_at_us >= 1000000) {
        snmp_operational_provider_t provider = atomic_load(&s_ops_provider);
        memset(&s_ops, 0, sizeof s_ops);
        if (provider) provider(&s_ops);
        s_ops_at_us = now;
        s_ops_valid = true;
    }
    return id > 0 && id < SNMP_OPS_LIMIT ? s_ops.value[id] : 0;
}

#define OPS_GETTER(n) static val_t g_ops_##n(void) { return (val_t){ .u = ops_metric(n) }; }
OPS_GETTER(1)  OPS_GETTER(2)  OPS_GETTER(3)  OPS_GETTER(4)  OPS_GETTER(5)
OPS_GETTER(6)  OPS_GETTER(7)  OPS_GETTER(8)  OPS_GETTER(9)  OPS_GETTER(10)
OPS_GETTER(11) OPS_GETTER(12) OPS_GETTER(13) OPS_GETTER(14) OPS_GETTER(15)
OPS_GETTER(16) OPS_GETTER(17) OPS_GETTER(18) OPS_GETTER(19) OPS_GETTER(20)
OPS_GETTER(21) OPS_GETTER(22) OPS_GETTER(23) OPS_GETTER(24) OPS_GETTER(25)
OPS_GETTER(26) OPS_GETTER(27)
_Static_assert(SNMP_OPS_LIMIT == 28, "add a getter and a MIB row per metric");
/* --- operational snapshot (end) --- */

/* Must be in ascending OID lexicographic order. */
static const mib_row_t s_mib[] = {
/* sysDescr        */ {{{1,3,6,1,2,1,1,1,0},9},            VT_STRING,    g_sysdescr},
/* sysUpTime       */ {{{1,3,6,1,2,1,1,3,0},9},            VT_TIMETICKS, g_sysuptime},
/* sysContact      */ {{{1,3,6,1,2,1,1,4,0},9},            VT_STRING,    g_syscontact},
/* sysName         */ {{{1,3,6,1,2,1,1,5,0},9},            VT_STRING,    g_sysname},
/* sysLocation     */ {{{1,3,6,1,2,1,1,6,0},9},            VT_STRING,    g_syslocation},
/* sysServices     */ {{{1,3,6,1,2,1,1,7,0},9},            VT_INT32,     g_sysservices},
/* ifNumber        */ {{{1,3,6,1,2,1,2,1,0},9},            VT_INT32,     g_ifnumber},
/* ifIndex.1       */ {{{1,3,6,1,2,1,2,2,1,1,1},11},       VT_INT32,     g_eth_ifindex},
/* ifIndex.2       */ {{{1,3,6,1,2,1,2,2,1,1,2},11},       VT_INT32,     g_wifi_ifindex},
/* ifIndex.3       */ {{{1,3,6,1,2,1,2,2,1,1,3},11},       VT_INT32,     g_ts_ifindex},
/* ifDescr.1       */ {{{1,3,6,1,2,1,2,2,1,2,1},11},       VT_STRING,    g_eth_ifdescr},
/* ifDescr.2       */ {{{1,3,6,1,2,1,2,2,1,2,2},11},       VT_STRING,    g_wifi_ifdescr},
/* ifDescr.3       */ {{{1,3,6,1,2,1,2,2,1,2,3},11},       VT_STRING,    g_ts_ifdescr},
/* ifType.1        */ {{{1,3,6,1,2,1,2,2,1,3,1},11},       VT_INT32,     g_eth_iftype},
/* ifType.2        */ {{{1,3,6,1,2,1,2,2,1,3,2},11},       VT_INT32,     g_wifi_iftype},
/* ifType.3        */ {{{1,3,6,1,2,1,2,2,1,3,3},11},       VT_INT32,     g_ts_iftype},
/* ifMtu.1         */ {{{1,3,6,1,2,1,2,2,1,4,1},11},       VT_INT32,     g_eth_ifmtu},
/* ifMtu.2         */ {{{1,3,6,1,2,1,2,2,1,4,2},11},       VT_INT32,     g_wifi_ifmtu},
/* ifMtu.3         */ {{{1,3,6,1,2,1,2,2,1,4,3},11},       VT_INT32,     g_ts_ifmtu},
/* ifSpeed.1       */ {{{1,3,6,1,2,1,2,2,1,5,1},11},       VT_GAUGE32,   g_eth_ifspeed},
/* ifSpeed.2       */ {{{1,3,6,1,2,1,2,2,1,5,2},11},       VT_GAUGE32,   g_wifi_ifspeed},
/* ifSpeed.3       */ {{{1,3,6,1,2,1,2,2,1,5,3},11},       VT_GAUGE32,   g_ts_ifspeed},
/* ifPhysAddr.1    */ {{{1,3,6,1,2,1,2,2,1,6,1},11},       VT_PHYS_ADDR, g_eth_ifphysaddr},
/* ifPhysAddr.2    */ {{{1,3,6,1,2,1,2,2,1,6,2},11},       VT_PHYS_ADDR, g_wifi_ifphysaddr},
/* ifPhysAddr.3    */ {{{1,3,6,1,2,1,2,2,1,6,3},11},       VT_STRING,    g_ts_ifphysaddr},
/* ifAdminStat.1   */ {{{1,3,6,1,2,1,2,2,1,7,1},11},       VT_INT32,     g_eth_ifadminstatus},
/* ifAdminStat.2   */ {{{1,3,6,1,2,1,2,2,1,7,2},11},       VT_INT32,     g_wifi_ifadminstatus},
/* ifAdminStat.3   */ {{{1,3,6,1,2,1,2,2,1,7,3},11},       VT_INT32,     g_ts_ifadminstatus},
/* ifOperStat.1    */ {{{1,3,6,1,2,1,2,2,1,8,1},11},       VT_INT32,     g_eth_ifoperstatus},
/* ifOperStat.2    */ {{{1,3,6,1,2,1,2,2,1,8,2},11},       VT_INT32,     g_wifi_ifoperstatus},
/* ifOperStat.3    */ {{{1,3,6,1,2,1,2,2,1,8,3},11},       VT_INT32,     g_ts_ifoperstatus},
/* ifInOctets.1    */ {{{1,3,6,1,2,1,2,2,1,10,1},11},      VT_COUNTER32, g_eth_rx_octets},
/* ifInOctets.2    */ {{{1,3,6,1,2,1,2,2,1,10,2},11},      VT_COUNTER32, g_wifi_rx_octets},
/* ifInOctets.3    */ {{{1,3,6,1,2,1,2,2,1,10,3},11},      VT_COUNTER32, g_ts_rx_octets},
/* ifInUcastPkts.1 */ {{{1,3,6,1,2,1,2,2,1,11,1},11},      VT_COUNTER32, g_eth_rx_pkts},
/* ifInUcastPkts.2 */ {{{1,3,6,1,2,1,2,2,1,11,2},11},      VT_COUNTER32, g_wifi_rx_pkts},
/* ifInUcastPkts.3 */ {{{1,3,6,1,2,1,2,2,1,11,3},11},      VT_COUNTER32, g_ts_rx_pkts},
/* ifOutOctets.1   */ {{{1,3,6,1,2,1,2,2,1,16,1},11},      VT_COUNTER32, g_eth_tx_octets},
/* ifOutOctets.2   */ {{{1,3,6,1,2,1,2,2,1,16,2},11},      VT_COUNTER32, g_wifi_tx_octets},
/* ifOutOctets.3   */ {{{1,3,6,1,2,1,2,2,1,16,3},11},      VT_COUNTER32, g_ts_tx_octets},
/* ifOutUcastPkts.1*/ {{{1,3,6,1,2,1,2,2,1,17,1},11},      VT_COUNTER32, g_eth_tx_pkts},
/* ifOutUcastPkts.2*/ {{{1,3,6,1,2,1,2,2,1,17,2},11},      VT_COUNTER32, g_wifi_tx_pkts},
/* ifOutUcastPkts.3*/ {{{1,3,6,1,2,1,2,2,1,17,3},11},      VT_COUNTER32, g_ts_tx_pkts},
/* --- HOST-RESOURCES-MIB: standard CPU + memory --- */
/* hrSystemUptime  */ {{{1,3,6,1,2,1,25,1,1,0},10},        VT_TIMETICKS, g_hr_uptime},
/* hrSystemProcs   */ {{{1,3,6,1,2,1,25,1,6,0},10},        VT_GAUGE32,   g_hr_processes},
/* hrMemorySize    */ {{{1,3,6,1,2,1,25,2,2,0},10},        VT_INT32,     g_hr_mem_size},
/* hrStorIndex.1   */ {{{1,3,6,1,2,1,25,2,3,1,1,1},12},    VT_INT32,     g_hrs_index1},
/* hrStorIndex.2   */ {{{1,3,6,1,2,1,25,2,3,1,1,2},12},    VT_INT32,     g_hrs_index2},
/* hrStorType.1    */ {{{1,3,6,1,2,1,25,2,3,1,2,1},12},    VT_OID,       g_hrs_type},
/* hrStorType.2    */ {{{1,3,6,1,2,1,25,2,3,1,2,2},12},    VT_OID,       g_hrs_type},
/* hrStorDescr.1   */ {{{1,3,6,1,2,1,25,2,3,1,3,1},12},    VT_STRING,    g_hrs_descr1},
/* hrStorDescr.2   */ {{{1,3,6,1,2,1,25,2,3,1,3,2},12},    VT_STRING,    g_hrs_descr2},
/* hrStorUnits.1   */ {{{1,3,6,1,2,1,25,2,3,1,4,1},12},    VT_INT32,     g_hrs_units},
/* hrStorUnits.2   */ {{{1,3,6,1,2,1,25,2,3,1,4,2},12},    VT_INT32,     g_hrs_units},
/* hrStorSize.1    */ {{{1,3,6,1,2,1,25,2,3,1,5,1},12},    VT_INT32,     g_hrs_size1},
/* hrStorSize.2    */ {{{1,3,6,1,2,1,25,2,3,1,5,2},12},    VT_INT32,     g_hrs_size2},
/* hrStorUsed.1    */ {{{1,3,6,1,2,1,25,2,3,1,6,1},12},    VT_INT32,     g_hrs_used1},
/* hrStorUsed.2    */ {{{1,3,6,1,2,1,25,2,3,1,6,2},12},    VT_INT32,     g_hrs_used2},
/* hrDeviceIndex.1 */ {{{1,3,6,1,2,1,25,3,2,1,1,1},12},    VT_INT32,     g_hr_dev_index0},
/* hrDeviceIndex.2 */ {{{1,3,6,1,2,1,25,3,2,1,1,2},12},    VT_INT32,     g_hr_dev_index1},
/* hrDeviceType.1  */ {{{1,3,6,1,2,1,25,3,2,1,2,1},12},    VT_OID,       g_hr_dev_type},
/* hrDeviceType.2  */ {{{1,3,6,1,2,1,25,3,2,1,2,2},12},    VT_OID,       g_hr_dev_type},
/* hrDeviceDescr.1 */ {{{1,3,6,1,2,1,25,3,2,1,3,1},12},    VT_STRING,    g_hr_dev_descr0},
/* hrDeviceDescr.2 */ {{{1,3,6,1,2,1,25,3,2,1,3,2},12},    VT_STRING,    g_hr_dev_descr1},
/* hrProcFrwID.1   */ {{{1,3,6,1,2,1,25,3,3,1,1,1},12},    VT_OID,       g_hr_frwid},
/* hrProcFrwID.2   */ {{{1,3,6,1,2,1,25,3,3,1,1,2},12},    VT_OID,       g_hr_frwid},
/* hrProcLoad.1    */ {{{1,3,6,1,2,1,25,3,3,1,2,1},12},    VT_INT32,     g_hr_cpu0_load},
/* hrProcLoad.2    */ {{{1,3,6,1,2,1,25,3,3,1,2,2},12},    VT_INT32,     g_hr_cpu1_load},
/* --- ENTITY-MIB: the sensor entPhySensorTable hangs off --- */
/* entPhysDescr.1  */ {{{1,3,6,1,2,1,47,1,1,1,1,2,1},13},  VT_STRING,    g_ent_descr},
/* entPhysContIn.1 */ {{{1,3,6,1,2,1,47,1,1,1,1,4,1},13},  VT_INT32,     g_ent_contained},
/* entPhysClass.1  */ {{{1,3,6,1,2,1,47,1,1,1,1,5,1},13},  VT_INT32,     g_ent_class},
/* entPhysRelPos.1 */ {{{1,3,6,1,2,1,47,1,1,1,1,6,1},13},  VT_INT32,     g_ent_relpos},
/* entPhysName.1   */ {{{1,3,6,1,2,1,47,1,1,1,1,7,1},13},  VT_STRING,    g_ent_name},
/* --- ENTITY-SENSOR-MIB: standard chip temperature --- */
/* entPhySensType.1*/ {{{1,3,6,1,2,1,99,1,1,1,1,1},12},    VT_INT32,     g_ents_type},
/* entPhySensScl.1 */ {{{1,3,6,1,2,1,99,1,1,1,2,1},12},    VT_INT32,     g_ents_scale},
/* entPhySensPrc.1 */ {{{1,3,6,1,2,1,99,1,1,1,3,1},12},    VT_INT32,     g_ents_prec},
/* entPhySensVal.1 */ {{{1,3,6,1,2,1,99,1,1,1,4,1},12},    VT_INT32,     g_ents_value},
/* entPhySensSts.1 */ {{{1,3,6,1,2,1,99,1,1,1,5,1},12},    VT_INT32,     g_ents_status},
/* entPhySensUni.1 */ {{{1,3,6,1,2,1,99,1,1,1,6,1},12},    VT_STRING,    g_ents_units},
/* entPhySensTs.1  */ {{{1,3,6,1,2,1,99,1,1,1,7,1},12},    VT_TIMETICKS, g_ents_ts},
/* entPhySensRate.1*/ {{{1,3,6,1,2,1,99,1,1,1,8,1},12},    VT_INT32,     g_ents_rate},
/* --- private tree: only what has no standard equivalent --- */
/* heapMinFree     */ {{{1,3,6,1,4,1,99999,1,1,4,0},11},   VT_GAUGE32,   g_heap_minfree},
/* ops.1           */ {{{1,3,6,1,4,1,99999,2,1,0},10},   VT_GAUGE32,   g_ops_1},
/* ops.2           */ {{{1,3,6,1,4,1,99999,2,2,0},10},   VT_GAUGE32,   g_ops_2},
/* ops.3           */ {{{1,3,6,1,4,1,99999,2,3,0},10},   VT_GAUGE32,   g_ops_3},
/* ops.4           */ {{{1,3,6,1,4,1,99999,2,4,0},10},   VT_GAUGE32,   g_ops_4},
/* ops.5           */ {{{1,3,6,1,4,1,99999,2,5,0},10},   VT_GAUGE32,   g_ops_5},
/* ops.6           */ {{{1,3,6,1,4,1,99999,2,6,0},10},   VT_GAUGE32,   g_ops_6},
/* ops.7           */ {{{1,3,6,1,4,1,99999,2,7,0},10},   VT_GAUGE32,   g_ops_7},
/* ops.8           */ {{{1,3,6,1,4,1,99999,2,8,0},10},   VT_GAUGE32,   g_ops_8},
/* ops.9           */ {{{1,3,6,1,4,1,99999,2,9,0},10},   VT_GAUGE32,   g_ops_9},
/* ops.10          */ {{{1,3,6,1,4,1,99999,2,10,0},10},   VT_GAUGE32,   g_ops_10},
/* ops.11          */ {{{1,3,6,1,4,1,99999,2,11,0},10},   VT_GAUGE32,   g_ops_11},
/* ops.12          */ {{{1,3,6,1,4,1,99999,2,12,0},10},   VT_GAUGE32,   g_ops_12},
/* ops.13          */ {{{1,3,6,1,4,1,99999,2,13,0},10},   VT_GAUGE32,   g_ops_13},
/* ops.14          */ {{{1,3,6,1,4,1,99999,2,14,0},10},   VT_GAUGE32,   g_ops_14},
/* ops.15          */ {{{1,3,6,1,4,1,99999,2,15,0},10},   VT_GAUGE32,   g_ops_15},
/* ops.16          */ {{{1,3,6,1,4,1,99999,2,16,0},10},   VT_GAUGE32,   g_ops_16},
/* ops.17          */ {{{1,3,6,1,4,1,99999,2,17,0},10},   VT_GAUGE32,   g_ops_17},
/* ops.18          */ {{{1,3,6,1,4,1,99999,2,18,0},10},   VT_GAUGE32,   g_ops_18},
/* ops.19          */ {{{1,3,6,1,4,1,99999,2,19,0},10},   VT_GAUGE32,   g_ops_19},
/* ops.20          */ {{{1,3,6,1,4,1,99999,2,20,0},10},   VT_GAUGE32,   g_ops_20},
/* ops.21          */ {{{1,3,6,1,4,1,99999,2,21,0},10},   VT_GAUGE32,   g_ops_21},
/* ops.22          */ {{{1,3,6,1,4,1,99999,2,22,0},10},   VT_GAUGE32,   g_ops_22},
/* ops.23          */ {{{1,3,6,1,4,1,99999,2,23,0},10},   VT_GAUGE32,   g_ops_23},
/* ops.24          */ {{{1,3,6,1,4,1,99999,2,24,0},10},   VT_GAUGE32,   g_ops_24},
/* ops.25          */ {{{1,3,6,1,4,1,99999,2,25,0},10},   VT_GAUGE32,   g_ops_25},
/* ops.26          */ {{{1,3,6,1,4,1,99999,2,26,0},10},   VT_GAUGE32,   g_ops_26},
/* ops.27          */ {{{1,3,6,1,4,1,99999,2,27,0},10},   VT_GAUGE32,   g_ops_27},
};
#define MIB_LEN ((int)(sizeof(s_mib)/sizeof(s_mib[0])))

static int oid_cmp(const uint32_t *a, int an, const uint32_t *b, int bn)
{
    int mn = an < bn ? an : bn;
    for (int i = 0; i < mn; i++) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return  1;
    }
    return an - bn;
}

static int mib_get(const uint32_t *arc, int n)
{
    for (int i = 0; i < MIB_LEN; i++)
        if (oid_cmp(arc, n, s_mib[i].oid.arc, s_mib[i].oid.n) == 0) return i;
    return -1;
}

static int mib_getnext(const uint32_t *arc, int n)
{
    for (int i = 0; i < MIB_LEN; i++)
        if (oid_cmp(s_mib[i].oid.arc, s_mib[i].oid.n, arc, n) > 0) return i;
    return -1;
}

static int encode_val(uint8_t *b, int cap, int row)
{
    val_t v = s_mib[row].get();
    switch (s_mib[row].vt) {
    case VT_STRING:    return ber_enc_str(b, cap, v.s);
    case VT_INT32:     return ber_enc_i32(b, cap, v.i);
    case VT_UINT32:    return ber_enc_u32(b, cap, 0x02, v.u);
    case VT_GAUGE32:   return ber_enc_u32(b, cap, 0x42, v.u);
    case VT_COUNTER32: return ber_enc_u32(b, cap, 0x41, v.u);
    case VT_TIMETICKS: return ber_enc_u32(b, cap, 0x43, v.u);
    case VT_PHYS_ADDR: return ber_enc_octstr(b, cap, (const uint8_t*)v.s, 6);
    case VT_OID:       return ber_enc_oid(b, cap, v.o->arc, v.o->n);
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* SNMP PDU parser / response builder                                 */
/* ------------------------------------------------------------------ */

static int process_pdu(const uint8_t *in, int inlen,
                       uint8_t *out, int outcap,
                       const char *community, snmp_buffers_t *buf)
{
    const uint8_t *p = in;
    int rem = inlen, len;

    if (ber_tlv(&p, &rem, &len) != 0x30) return -1;
    if (len < rem) rem = len;              /* ignore any trailing garbage */

    /* version */
    if (ber_tlv(&p, &rem, &len) != 0x02 || len != 1 || p[0] > 1) return -1;
    int version = p[0];
    p += len; rem -= len;

    /* community */
    if (ber_tlv(&p, &rem, &len) != 0x04) return -1;
    int comlen = (int)strlen(community);
    if (len != comlen || memcmp(p, community, len) != 0) return -1;
    p += len; rem -= len;

    /* PDU */
    int pdu_tag = ber_tlv(&p, &rem, &len);
    if (pdu_tag != 0xa0 && pdu_tag != 0xa1 && pdu_tag != 0xa5) return -1;
    rem = len;                             /* confine parsing to the PDU */

    /* request-id. Echoed verbatim into the reply, so cap it at a sane
     * width — pdu_body below is a fixed buffer and a wire-supplied length
     * must never decide how much we copy into it. */
    const uint8_t *rid_tlv = p;
    if (ber_tlv(&p, &rem, &len) != 0x02 || len < 1 || len > 4) return -1;
    int req_id_tlen = (int)(p - rid_tlv) + len;
    p += len; rem -= len;

    /* error-status and error-index: ignored on input, zeroed on output.
     * In a GETBULK these two are non-repeaters / max-repetitions instead;
     * we answer one successor per varbind regardless, which is a legal if
     * unhelpful reply — bulk walkers simply take more round trips. */
    for (int k = 0; k < 2; k++) {
        if (ber_tlv(&p, &rem, &len) != 0x02 || len < 1 || len > 4) return -1;
        p += len; rem -= len;
    }

    /* varbind list */
    if (ber_tlv(&p, &rem, &len) != 0x30) return -1;
    rem = len;

    uint8_t *vbl_buf = buf->vbl_buf;
    int vbl_pos = 0;
    bool get_next = (pdu_tag == 0xa1 || pdu_tag == 0xa5);

    while (rem > 0) {
        int vblen;
        if (ber_tlv(&p, &rem, &vblen) != 0x30) return -1;
        const uint8_t *vbp = p;
        int vbrem = vblen;
        p += vblen; rem -= vblen;

        int oidlen;
        if (ber_tlv(&vbp, &vbrem, &oidlen) != 0x06) return -1;
        uint32_t arc[MAX_OID]; int an;
        if (!ber_dec_oid(vbp, oidlen, arc, &an, MAX_OID)) return -1;

        int row = get_next ? mib_getnext(arc, an) : mib_get(arc, an);

        uint8_t *vb = buf->vb; int vbpos = 0;
        if (row < 0) {
            int oidhdrlen = ber_enc_oid(vb + vbpos, VB_BUF - vbpos, arc, an);
            if (!oidhdrlen) return -1;
            vbpos += oidhdrlen;
            /* v2c exception tags. A GETNEXT that ran off the end of the MIB
             * is endOfMibView (0x82); a GET for an object we do not implement
             * is noSuchObject (0x80). Returning 0x80 for both makes a
             * conformant walker retry the same OID forever, since nothing
             * tells it the walk is finished. v1 has no exceptions: NULL. */
            if (version >= 1) { vb[vbpos++] = get_next ? 0x82 : 0x80; vb[vbpos++] = 0x00; }
            else              { vb[vbpos++] = 0x05; vb[vbpos++] = 0x00; }
        } else {
            int oidhdrlen = ber_enc_oid(vb + vbpos, VB_BUF - vbpos,
                                        s_mib[row].oid.arc, s_mib[row].oid.n);
            if (!oidhdrlen) return -1;
            vbpos += oidhdrlen;
            int valen = encode_val(vb + vbpos, VB_BUF - vbpos, row);
            if (!valen) return -1;
            vbpos += valen;
        }
        uint8_t hdr[4]; int hl = seq_hdr(hdr, sizeof(hdr), 0x30, vbpos);
        if (!hl || vbl_pos + hl + vbpos > VBL_BUF) return -1;
        memcpy(vbl_buf + vbl_pos, hdr, hl); vbl_pos += hl;
        memcpy(vbl_buf + vbl_pos, vb, vbpos); vbl_pos += vbpos;
    }

    uint8_t *pdu_body = buf->pdu_body; int pb = 0;
    memcpy(pdu_body, rid_tlv, req_id_tlen);
    pb += req_id_tlen;
    pdu_body[pb++] = 0x02; pdu_body[pb++] = 0x01; pdu_body[pb++] = 0x00;
    pdu_body[pb++] = 0x02; pdu_body[pb++] = 0x01; pdu_body[pb++] = 0x00;
    uint8_t vbl_hdr[4]; int vhl = seq_hdr(vbl_hdr, sizeof(vbl_hdr), 0x30, vbl_pos);
    if (!vhl || pb + vhl + vbl_pos > PDU_BODY_BUF) return -1;
    memcpy(pdu_body + pb, vbl_hdr, vhl); pb += vhl;
    memcpy(pdu_body + pb, vbl_buf, vbl_pos); pb += vbl_pos;

    uint8_t pdu_hdr[4]; int phl = seq_hdr(pdu_hdr, sizeof(pdu_hdr), 0xa2, pb);
    if (!phl) return -1;

    uint8_t *comm_tlv = buf->comm_tlv;
    int ctlen = ber_enc_str(comm_tlv, COMM_TLV_BUF, community);
    if (!ctlen) return -1;

    uint8_t ver_tlv[3] = { 0x02, 0x01, (uint8_t)version };
    int vtlen = 3;

    int inner = vtlen + ctlen + phl + pb;
    uint8_t outer_hdr[4]; int ohl = seq_hdr(outer_hdr, sizeof(outer_hdr), 0x30, inner);
    if (!ohl) return -1;
    int total = ohl + inner;
    if (total > outcap) return -1;

    uint8_t *op = out;
    memcpy(op, outer_hdr, ohl); op += ohl;
    memcpy(op, ver_tlv, vtlen); op += vtlen;
    memcpy(op, comm_tlv, ctlen); op += ctlen;
    memcpy(op, pdu_hdr, phl); op += phl;
    memcpy(op, pdu_body, pb);
    return total;
}

/* ------------------------------------------------------------------ */
/* SNMP task                                                          */
/* ------------------------------------------------------------------ */
static void stop_telemetry_timer(void)
{
    if (!s_cpu_timer) return;
    esp_timer_stop(s_cpu_timer);
    esp_timer_delete(s_cpu_timer);
    s_cpu_timer = NULL;
    s_cpu0_usage = 0;
    s_cpu1_usage = 0;
    s_ts_up = false;
}

static void start_telemetry_timer(void)
{
    s_prev_wall_us = (uint64_t)esp_timer_get_time();
    s_prev_idle0_us = 0;
    s_prev_idle1_us = 0;
    esp_timer_create_args_t targs = {
        .callback = telemetry_tick_cb,
        .name     = "snmp_tick",
    };
    if (esp_timer_create(&targs, &s_cpu_timer) != ESP_OK ||
        esp_timer_start_periodic(s_cpu_timer,
                                 (uint64_t)CPU_SAMPLE_S * 1000000ULL) != ESP_OK) {
        ESP_LOGW(TAG, "CPU telemetry timer unavailable");
        if (s_cpu_timer) {
            esp_timer_delete(s_cpu_timer);
            s_cpu_timer = NULL;
        }
    }
}

static void snmp_task(void *arg);

/* The caller has already set s_starting while holding s_mutex. */
static void start_snmp_task_reserved(void)
{
    if (xTaskCreate(snmp_task, "snmp_agent", TASK_STACK, NULL,
                    tskIDLE_PRIORITY + 2, NULL) == pdPASS)
        return;

    ESP_LOGE(TAG, "failed to create task");
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    s_starting = false;
    xSemaphoreGive(s_mutex);
}

static void start_snmp_task_if_needed(void)
{
    bool start = false;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    if (s_enabled && !s_running && !s_starting && !s_stopping) {
        s_starting = true;
        start = true;
    }
    xSemaphoreGive(s_mutex);
    if (start) start_snmp_task_reserved();
}

static void snmp_task(void *arg)
{
    (void)arg;
    int sock = -1;
    bool socket_published = false;
    snmp_buffers_t *buf = heap_caps_malloc(sizeof(*buf),
                                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        ESP_LOGE(TAG, "PSRAM allocation failed");
        goto done;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    bool enabled = s_enabled;
    xSemaphoreGive(s_mutex);
    if (!enabled) goto done;

    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { ESP_LOGE(TAG, "socket() failed"); goto done; }

    /* Only this task closes its descriptor. A bounded receive also lets it
     * observe disable if UDP shutdown does not wake recvfrom on this SDK. */
    struct timeval timeout = { .tv_sec = 1, .tv_usec = 0 };
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0)
        goto done;

    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port   = htons(SNMP_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ESP_LOGE(TAG, "bind(:161) failed");
        goto done;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    if (s_enabled) {
        s_sock = sock;
        s_running = true;
        s_starting = false;
        socket_published = true;
    }
    xSemaphoreGive(s_mutex);
    if (!socket_published) goto done;

    atomic_store(&s_hooks_enabled, true);
    install_traffic_hooks();
    start_telemetry_timer();
    ESP_LOGI(TAG, "listening on 0.0.0.0:161");

    while (true) {
        xSemaphoreTake(s_mutex, portMAX_DELAY);
        enabled = s_enabled && !s_stopping;
        xSemaphoreGive(s_mutex);
        if (!enabled) break;
        struct sockaddr_in src; socklen_t srclen = sizeof(src);
        int rlen = recvfrom(sock, buf->rx, sizeof(buf->rx), 0,
                            (struct sockaddr *)&src, &srclen);
        if (rlen < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            break;
        }

        xSemaphoreTake(s_mutex, portMAX_DELAY);
        enabled = s_enabled && !s_stopping;
        /* Keep the configuration stable while encoding a reply. The task
         * owns the descriptor until teardown, so a disable cannot recycle
         * its number underneath recvfrom/sendto. */
        bool sock_ours = (s_sock == sock);
        char comm[256]; strncpy(comm, s_strings->community, sizeof(comm)); comm[255] = '\0';
        if (!sock_ours || !enabled) { xSemaphoreGive(s_mutex); break; }

        int rsp = process_pdu(buf->rx, rlen, buf->tx, sizeof(buf->tx), comm, buf);
        if (rsp > 0)
            sendto(sock, buf->tx, rsp, 0, (struct sockaddr *)&src, srclen);
        xSemaphoreGive(s_mutex);
    }

done:
    atomic_store(&s_hooks_enabled, false);
    stop_telemetry_timer();
    uninstall_traffic_hooks();

    bool close_sock = sock >= 0;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    if (socket_published && s_sock == sock) {
        s_sock = -1;
    }
    if (close_sock && sock >= 0) close(sock);
    s_running = false;
    s_starting = false;
    bool restart = s_enabled && s_stopping;
    s_stopping = false;
    if (restart) s_starting = true;
    xSemaphoreGive(s_mutex);

    if (buf) heap_caps_free(buf);
    if (restart) start_snmp_task_reserved();
    vTaskDelete(NULL);
}

/* ------------------------------------------------------------------ */
/* NVS helpers                                                        */
/* ------------------------------------------------------------------ */
static void nvs_read_str(nvs_handle_t h, const char *key, char *buf,
                         size_t sz, const char *def)
{
    size_t len = sz;
    if (nvs_get_str(h, key, buf, &len) != ESP_OK)
        snprintf(buf, sz, "%s", def);
}

static void load_nvs(void)
{
    nvs_handle_t h;
    if (nvs_open("tsr", NVS_READONLY, &h) != ESP_OK) {
        snprintf(s_strings->community, sizeof s_strings->community, "public");
        snprintf(s_strings->sysname, sizeof s_strings->sysname, "esp32-router");
        s_strings->syscontact[0] = '\0'; s_strings->syslocation[0] = '\0';
        return;
    }
    size_t sz = 0;
    if (nvs_get_blob(h, SNMP_NVS_KEY_CONFIG, NULL, &sz) == ESP_OK) {
        snmp_persist_t *cfg = sz == sizeof(snmp_persist_t)
            ? heap_caps_malloc(sizeof(*cfg), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
            : NULL;
        if (cfg && nvs_get_blob(h, SNMP_NVS_KEY_CONFIG, cfg, &sz) == ESP_OK &&
            sz == sizeof(*cfg) && cfg->magic == SNMP_CONFIG_MAGIC &&
            memchr(cfg->community, 0, sizeof(cfg->community)) &&
            memchr(cfg->sysname, 0, sizeof(cfg->sysname)) &&
            memchr(cfg->syscontact, 0, sizeof(cfg->syscontact)) &&
            memchr(cfg->syslocation, 0, sizeof(cfg->syslocation))) {
            s_enabled = cfg->enabled != 0;
            memcpy(s_strings->community, cfg->community, sizeof(cfg->community));
            memcpy(s_strings->sysname, cfg->sysname, sizeof(cfg->sysname));
            memcpy(s_strings->syscontact, cfg->syscontact, sizeof(cfg->syscontact));
            memcpy(s_strings->syslocation, cfg->syslocation, sizeof(cfg->syslocation));
            heap_caps_free(cfg);
            nvs_close(h);
            return;
        }
        if (cfg) heap_caps_free(cfg);
        ESP_LOGE(TAG, "invalid or unreadable SNMP config blob; disabled");
        nvs_close(h);
        return;
    }
    uint8_t en = 0;
    nvs_get_u8(h, SNMP_NVS_KEY_EN, &en);
    s_enabled = en != 0;
    nvs_read_str(h, SNMP_NVS_KEY_COMM,     s_strings->community,   sizeof s_strings->community,   "public");
    nvs_read_str(h, SNMP_NVS_KEY_NAME,     s_strings->sysname,     sizeof s_strings->sysname,     "esp32-router");
    nvs_read_str(h, SNMP_NVS_KEY_CONTACT,  s_strings->syscontact,  sizeof s_strings->syscontact,  "");
    nvs_read_str(h, SNMP_NVS_KEY_LOCATION, s_strings->syslocation, sizeof s_strings->syslocation, "");
    nvs_close(h);
}

/* ------------------------------------------------------------------ */
/* Public API                                                         */
/* ------------------------------------------------------------------ */
void snmp_agent_init(void)
{
    /* Status and diagnostics need the temperature sensor even if SNMP's
     * configuration allocation fails or the listener is disabled. */
    temperature_sensor_config_t tcfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    if (temperature_sensor_install(&tcfg, &s_temp_sensor) == ESP_OK)
        temperature_sensor_enable(s_temp_sensor);
    else
        s_temp_sensor = NULL;

    s_mutex = xSemaphoreCreateMutex();
    if (!s_mutex) {
        ESP_LOGE(TAG, "failed to create configuration mutex");
        return;
    }
    s_strings = heap_caps_calloc(1, sizeof(*s_strings),
                                 MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!s_strings) {
        ESP_LOGE(TAG, "PSRAM allocation failed for configuration");
        return;
    }

    load_nvs();

    /* Older firmware accepted an empty community. Fail closed for any such
     * persisted configuration; POST can set a new community before enabling. */
    if (s_enabled && s_strings->community[0] == '\0') {
        ESP_LOGE(TAG, "disabled SNMP: stored community is empty");
        s_enabled = false;
    }

    /* mib_getnext() is a linear first-greater scan, so s_mib must be sorted.
     * A mis-ordered row silently truncates every walk at that point, which
     * is thoroughly unpleasant to debug from the far end — check once here
     * so a future edit says so out loud. */
    for (int i = 1; i < MIB_LEN; i++)
        if (oid_cmp(s_mib[i-1].oid.arc, s_mib[i-1].oid.n,
                    s_mib[i].oid.arc,   s_mib[i].oid.n) >= 0)
            ESP_LOGE(TAG, "MIB table out of order at row %d — walks will truncate", i);

    const esp_app_desc_t *desc = esp_app_get_description();
    snprintf(s_strings->sysdescr, sizeof s_strings->sysdescr, "ESP32 Tailscale Router %s",
             desc ? desc->version : "?");

    if (!s_enabled) { ESP_LOGI(TAG, "disabled"); return; }
    start_snmp_task_if_needed();
}

void snmp_agent_apply_live(bool enabled,
                           const char *community,
                           const char *sys_name,
                           const char *sys_contact,
                           const char *sys_location)
{
    if (!s_strings) {
        ESP_LOGE(TAG, "configuration storage unavailable");
        return;
    }
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    s_enabled = enabled;
    if (community)    snprintf(s_strings->community,   sizeof s_strings->community,   "%s", community);
    if (sys_name)     snprintf(s_strings->sysname,     sizeof s_strings->sysname,     "%s", sys_name);
    if (sys_contact)  snprintf(s_strings->syscontact,  sizeof s_strings->syscontact,  "%s", sys_contact);
    if (sys_location) snprintf(s_strings->syslocation, sizeof s_strings->syslocation, "%s", sys_location);
    if (!enabled) {
        s_stopping = s_running || s_starting;
        /* Wake the owner, but do not close/recycle its descriptor here. */
        if (s_sock >= 0) shutdown(s_sock, SHUT_RDWR);
    }
    xSemaphoreGive(s_mutex);
    if (enabled) start_snmp_task_if_needed();
}

esp_err_t snmp_agent_save_config(bool enabled,
                                 const char *community,
                                 const char *sys_name,
                                 const char *sys_contact,
                                 const char *sys_location)
{
    if (!s_strings || !community || (enabled && !community[0]) || !sys_name ||
        !sys_contact || !sys_location ||
        strnlen(community, 256) >= 256 || strnlen(sys_name, 256) >= 256 ||
        strnlen(sys_contact, 256) >= 256 || strnlen(sys_location, 256) >= 256)
        return ESP_ERR_INVALID_ARG;

    snmp_persist_t *cfg = heap_caps_calloc(1, sizeof(*cfg),
                                           MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!cfg) return ESP_ERR_NO_MEM;
    cfg->magic = SNMP_CONFIG_MAGIC;
    cfg->enabled = enabled ? 1 : 0;
    strcpy(cfg->community, community);
    strcpy(cfg->sysname, sys_name);
    strcpy(cfg->syscontact, sys_contact);
    strcpy(cfg->syslocation, sys_location);

    nvs_handle_t h;
    esp_err_t err = nvs_open("tsr", NVS_READWRITE, &h);
    if (err == ESP_OK) {
        err = nvs_set_blob(h, SNMP_NVS_KEY_CONFIG, cfg, sizeof(*cfg));
        if (err == ESP_OK) err = nvs_commit(h);
        nvs_close(h);
    }
    heap_caps_free(cfg);
    if (err == ESP_OK)
        snmp_agent_apply_live(enabled, community, sys_name, sys_contact, sys_location);
    return err;
}

bool snmp_agent_is_enabled(void)
{
    if (!s_mutex) return false;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    bool enabled = s_enabled;
    xSemaphoreGive(s_mutex);
    return enabled;
}

bool snmp_agent_is_running(void)
{
    if (!s_mutex) return false;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    bool running = s_running && s_enabled && !s_stopping;
    xSemaphoreGive(s_mutex);
    return running;
}

void snmp_agent_get_config(bool *enabled_out, bool *running_out,
                           char *community,    size_t comm_sz,
                           char *sys_name,     size_t name_sz,
                           char *sys_contact,  size_t cont_sz,
                           char *sys_location, size_t loc_sz)
{
    if (!s_strings) {
        *enabled_out = false;
        *running_out = false;
        if (comm_sz) community[0] = '\0';
        if (name_sz) sys_name[0] = '\0';
        if (cont_sz) sys_contact[0] = '\0';
        if (loc_sz)  sys_location[0] = '\0';
        return;
    }
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    *enabled_out = s_enabled;
    *running_out = s_running && s_enabled && !s_stopping;
    snprintf(community,    comm_sz, "%s", s_strings->community);
    snprintf(sys_name,     name_sz, "%s", s_strings->sysname);
    snprintf(sys_contact,  cont_sz, "%s", s_strings->syscontact);
    snprintf(sys_location, loc_sz,  "%s", s_strings->syslocation);
    xSemaphoreGive(s_mutex);
}
