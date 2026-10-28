/* Event and metrics history; see history.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "history.h"
#include "esp_system.h"
#include <stdio.h>
#include <string.h>

/* --- history core (begin) --- */
static void put16(uint8_t *p, uint16_t v) {p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);}
static void put32(uint8_t *p, uint32_t v) {put16(p, (uint16_t)v); put16(p + 2, (uint16_t)(v >> 16));}
static uint16_t get16(const uint8_t *p) {return (uint16_t)(p[0] | p[1] << 8);}
static uint32_t get32(const uint8_t *p) {return get16(p) | (uint32_t)get16(p + 2) << 16;}

void history_sample_pack(const history_sample_t *s, uint8_t out[HIST_SAMPLE_BYTES])
{
    put16(out, s->boot); out[2] = (uint8_t)s->rssi; out[3] = s->cpu;
    put32(out + 4, s->int_free); put32(out + 8, s->int_largest); put32(out + 12, s->psram_free);
    put32(out + 16, s->rx); put32(out + 20, s->tx);
    out[24] = s->peers; out[25] = s->flags; put16(out + 26, (uint16_t)s->temp);
}

bool history_sample_unpack(const uint8_t *in, size_t len, uint32_t wall, uint32_t uptime, history_sample_t *out)
{
    if (!in || !out || len != HIST_SAMPLE_BYTES) return false;
    memset(out, 0, sizeof *out);
    out->wall = wall; out->uptime = uptime;
    out->boot = get16(in); out->rssi = (int8_t)in[2]; out->cpu = in[3];
    out->int_free = get32(in + 4); out->int_largest = get32(in + 8); out->psram_free = get32(in + 12);
    out->rx = get32(in + 16); out->tx = get32(in + 20);
    out->peers = in[24]; out->flags = in[25]; out->temp = (int16_t)get16(in + 26);
    return out->cpu <= 100 || out->cpu == 0xFF;
}

static uint32_t sat_add(uint32_t a, uint32_t b) {return a > UINT32_MAX - b ? UINT32_MAX : a + b;}
static uint32_t min32(uint32_t a, uint32_t b) {return a < b ? a : b;}

void history_agg_add(history_agg_t *a, const history_sample_t *s)
{
    if (!a->count) {
        a->s = *s;
    } else {
        a->s.int_free = min32(a->s.int_free, s->int_free);
        a->s.int_largest = min32(a->s.int_largest, s->int_largest);
        a->s.psram_free = min32(a->s.psram_free, s->psram_free);
        a->s.rx = sat_add(a->s.rx, s->rx); a->s.tx = sat_add(a->s.tx, s->tx);
        if (s->peers > a->s.peers) a->s.peers = s->peers;
        a->s.flags &= s->flags;
        /* The newest point stamps the interval, whatever the adding order. */
        if (s->boot > a->s.boot || (s->boot == a->s.boot && s->uptime > a->s.uptime)) {
            a->s.boot = s->boot; a->s.uptime = s->uptime; a->s.wall = s->wall;
        }
    }
    a->count++;
    if (s->rssi) {a->rssi_sum += s->rssi; a->rssi_n++;}
    if (s->cpu <= 100) {a->cpu_sum += s->cpu; a->cpu_n++;}
    if (s->temp != INT16_MIN) {a->temp_sum += s->temp; a->temp_n++;}
}

bool history_agg_result(const history_agg_t *a, history_sample_t *out)
{
    if (!a || !a->count) return false;
    *out = a->s;
    out->rssi = a->rssi_n ? (int8_t)(a->rssi_sum / (int32_t)a->rssi_n) : 0;
    out->cpu = a->cpu_n ? (uint8_t)(a->cpu_sum / a->cpu_n) : 0xFF;
    out->temp = a->temp_n ? (int16_t)(a->temp_sum / (int32_t)a->temp_n) : INT16_MIN;
    return true;
}

bool history_rate_allow(history_rate_t *r, uint32_t now)
{
    if (!r->started) {r->started = true; r->tokens = HIST_RATE_BURST; r->last = now;}
    if (now > r->last) {
        uint32_t add = (now - r->last) / 3;
        if (add) {r->tokens = min32(HIST_RATE_BURST, sat_add(r->tokens, add)); r->last += add * 3;}
    }
    if (!r->tokens) return false;
    r->tokens--;
    return true;
}

size_t history_json_escape(char *out, size_t cap, const char *in)
{
    size_t n = 0;
    if (!out || !cap) return 0;
    for (; in && *in; in++) {
        unsigned char c = (unsigned char)*in;
        char tmp[8];
        size_t len;
        if (c == '"' || c == '\\') {tmp[0] = '\\'; tmp[1] = (char)c; len = 2;}
        else if (c < 0x20 || c == 0x7F) len = (size_t)snprintf(tmp, sizeof tmp, "\\u%04x", c);
        else {tmp[0] = (char)c; len = 1;}
        if (n + len >= cap) break;
        memcpy(out + n, tmp, len);
        n += len;
    }
    /* Never end on half a UTF-8 sequence. */
    size_t keep = n;
    while (keep && ((unsigned char)out[keep - 1] & 0xC0) == 0x80) keep--;
    if (keep && ((unsigned char)out[keep - 1] & 0x80)) {
        unsigned char lead = (unsigned char)out[keep - 1];
        size_t need = lead >= 0xF0 ? 4 : lead >= 0xE0 ? 3 : lead >= 0xC0 ? 2 : 1;
        if (n - (keep - 1) == need) keep = n; else keep--;
    } else keep = n;
    out[keep] = 0;
    return keep;
}

const char *history_kind_name(unsigned kind)
{
    static const char *const names[] = {"event", "boot", "crash", "update", "uplink", "tailnet", "settings", "security", "storage", "service"};
    return kind < sizeof names / sizeof names[0] ? names[kind] : "event";
}

const char *history_level_name(unsigned level) {return level == HIST_ERROR ? "error" : level == HIST_WARN ? "warn" : "info";}

bool history_point_age(uint32_t now_wall, uint32_t now_up, uint16_t now_boot,
                       uint32_t wall, uint32_t up, uint16_t boot, uint32_t *age)
{
    if (boot == now_boot && up <= now_up) {*age = now_up - up; return true;}   /* exact within a boot */
    if (now_wall && wall && wall <= now_wall) {*age = now_wall - wall; return true;}
    return false;
}
/* --- history core (end) --- */

#ifdef ESP_PLATFORM
#include "json_guard.h"
#include "netif_hooks.h"
#include "nvs_params.h"
#include "reset_history.h"
#include "runtime_metrics.h"
#include "storage_store.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "microlink.h"
#include "esp_app_desc.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <time.h>

static const char *TAG = "history";
extern volatile int ap_connect;

#define EV_TYPE 1                /* record types in the rings */
#define MX_TYPE 2
#define QUEUE_LEN 16
#define LIVE_SAMPLES 360         /* 6 h of 1-minute samples */
#define MERGE_SAMPLES 10         /* one persisted point per 10 minutes */
#define SAMPLE_PERIOD 60
#define POLL_PERIOD 5

typedef struct {uint8_t kind, level; uint32_t wall, uptime; char text[HIST_TEXT_MAX + 1];} queued_t;
typedef struct {bool events, metrics, snapshots;} hist_config_t;

/* Everything below exists only while a feature is on: the task, its stack
 * and the PSRAM buffers are allocated when switched on and released when
 * switched off. Off, history_event() is one atomic load. */
static SemaphoreHandle_t s_lock;            /* task lifecycle, live ring, config */
static StaticSemaphore_t s_lock_storage;
static hist_config_t s_cfg;
static atomic_bool s_events_on;           /* events are accepted: stored or sunk */
static volatile history_sink_t s_sink;
static history_sink_poll_t s_sink_poll;
static bool s_inited;
static QueueHandle_t s_queue;               /* kept once created (producers may race a switch-off) */
static atomic_uint s_dropped;
static unsigned s_limited;
static TaskHandle_t s_task;
static history_sample_t *s_live;            /* PSRAM, LIVE_SAMPLES */
static unsigned s_live_head, s_live_count;
EXT_RAM_BSS_ATTR static store_ring_t s_events, s_metrics;
static bool s_persist, s_rings_open;
static uint16_t s_boot;

static uint32_t uptime_s(void) {return (uint32_t)(esp_timer_get_time() / 1000000);}
static uint32_t wall_now(void) {time_t t = time(NULL); return t > 1700000000 ? (uint32_t)t : 0;}
uint16_t history_boot_number(void) {return s_boot;}

void history_event(history_kind_t kind, history_level_t level, const char *fmt, ...)
{
    if (!atomic_load_explicit(&s_events_on, memory_order_acquire) || !s_queue) return;
    queued_t e = {.kind = (uint8_t)kind, .level = (uint8_t)level, .wall = wall_now(), .uptime = uptime_s()};
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(e.text, sizeof e.text, fmt, ap);
    va_end(ap);
    if (xQueueSend(s_queue, &e, 0) != pdTRUE) atomic_fetch_add(&s_dropped, 1);
}

static void write_event(const queued_t *e)
{
    uint8_t payload[3 + HIST_TEXT_MAX];
    size_t len = strnlen(e->text, HIST_TEXT_MAX);
    payload[0] = e->level; put16(payload + 1, s_boot);
    memcpy(payload + 3, e->text, len);
    storage_store_lock();
    esp_err_t err = store_ring_append(&s_events, e->kind, e->wall, e->uptime, payload, (uint16_t)(3 + len));
    storage_store_unlock();
    if (err) ESP_LOGW(TAG, "event not stored: %s", esp_err_to_name(err));
}

/* --- metrics --- */
static uint64_t s_last_rx, s_last_tx;
static bool s_have_traffic;
EXT_RAM_BSS_ATTR static history_agg_t s_merge;

static void take_sample(history_sample_t *s)
{
    memset(s, 0, sizeof *s);
    s->uptime = uptime_s(); s->wall = wall_now(); s->boot = s_boot;
    s->int_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    s->int_largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    s->psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    uint64_t rx = netif_hooks_get_sta_bytes_in() + netif_hooks_get_ppp_bytes_in();
    uint64_t tx = netif_hooks_get_sta_bytes_out() + netif_hooks_get_ppp_bytes_out();
    if (s_have_traffic && rx >= s_last_rx && tx >= s_last_tx) {
        uint64_t drx = rx - s_last_rx, dtx = tx - s_last_tx;
        s->rx = drx > UINT32_MAX ? UINT32_MAX : (uint32_t)drx;
        s->tx = dtx > UINT32_MAX ? UINT32_MAX : (uint32_t)dtx;
    }
    s_last_rx = rx; s_last_tx = tx; s_have_traffic = true;
    wifi_ap_record_t ap;
    if (ap_connect && esp_wifi_sta_get_ap_info(&ap) == ESP_OK) s->rssi = ap.rssi;
    runtime_metrics_t cpu = runtime_metrics_get();
    s->cpu = cpu.valid ? cpu.load_pct : 0xFF;
    s->temp = INT16_MIN;          /* the sensor draws current: not sampled here */
    bool tailnet = tailscale_is_connected();
    microlink_t *ml = tailnet ? tailscale_get_microlink() : NULL;
    if (ml) {
        int count = microlink_get_peer_count(ml), online = 0;
        for (int i = 0; i < count; i++) {
            microlink_peer_info_t peer = {0};
            if (microlink_get_peer_info(ml, i, &peer) == ESP_OK && peer.online) online++;
        }
        s->peers = online > 255 ? 255 : (uint8_t)online;
    }
    s->flags = (ap_connect ? HIST_UP_UPLINK : 0) | (tailnet ? HIST_UP_TAILNET : 0);
}

static void store_sample(const history_sample_t *s)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_live) {
        s_live[s_live_head] = *s;
        s_live_head = (s_live_head + 1) % LIVE_SAMPLES;
        if (s_live_count < LIVE_SAMPLES) s_live_count++;
    }
    xSemaphoreGive(s_lock);
    history_agg_add(&s_merge, s);
    if (s_merge.count < MERGE_SAMPLES) return;
    history_sample_t merged;
    if (s_persist && history_agg_result(&s_merge, &merged)) {
        uint8_t payload[HIST_SAMPLE_BYTES];
        history_sample_pack(&merged, payload);
        storage_store_lock();
        esp_err_t err = store_ring_append(&s_metrics, MX_TYPE, merged.wall, merged.uptime, payload, sizeof payload);
        storage_store_unlock();
        if (err) ESP_LOGW(TAG, "metrics not stored: %s", esp_err_to_name(err));
    }
    memset(&s_merge, 0, sizeof s_merge);
}

static void history_task(void *arg)
{
    (void)arg;
    history_rate_t rate = {0};
    uint32_t next_sample = uptime_s() + SAMPLE_PERIOD, next_poll = 0;
    int tailnet_state = -1, tailnet_seen = -1;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        xSemaphoreTake(s_lock, portMAX_DELAY);
        hist_config_t cfg = s_cfg;
        if (!cfg.metrics && s_live) {free(s_live); s_live = NULL; s_live_count = s_live_head = 0;}
        history_sink_t sink = s_sink;
        history_sink_poll_t poll = s_sink_poll;
        if (!cfg.events && !cfg.metrics && !sink) {
            s_task = NULL;
            xSemaphoreGive(s_lock);
            vTaskDelete(NULL);
        }
        xSemaphoreGive(s_lock);
        uint32_t now = uptime_s();
        queued_t e;
        for (int i = 0; i < 8 && s_queue && xQueueReceive(s_queue, &e, 0) == pdTRUE; i++) {
            if (sink) sink(e.kind, e.level, e.wall, e.text);
            if (!cfg.events || !s_persist) continue;
            if (!history_rate_allow(&rate, now)) {s_limited++; continue;}
            write_event(&e);
        }
        if (sink && poll) poll();
        unsigned dropped = atomic_exchange(&s_dropped, 0);
        if (cfg.events && (dropped || s_limited) && history_rate_allow(&rate, now)) {
            queued_t note = {.kind = HIST_EV_STORAGE, .level = HIST_WARN, .wall = wall_now(), .uptime = now};
            snprintf(note.text, sizeof note.text, "%u events not recorded (too many at once)", dropped + s_limited);
            if (s_persist) write_event(&note);
            s_limited = 0;
        }
        if ((cfg.events || sink) && now >= next_poll) {
            next_poll = now + POLL_PERIOD;
            int state = tailscale_is_connected();
            if (state == tailnet_seen && state != tailnet_state) {   /* stable for two polls */
                if (tailnet_state != -1 || state)
                    history_event(HIST_EV_TAILNET, state ? HIST_INFO : HIST_WARN,
                                  state ? "Tailnet connected" : "Tailnet connection lost");
                tailnet_state = state;
            }
            tailnet_seen = state;
        }
        if (cfg.metrics && now >= next_sample) {
            next_sample = now + SAMPLE_PERIOD;
            history_sample_t s;
            take_sample(&s);
            store_sample(&s);
        }
    }
}

static void open_rings(void)
{
    if (s_rings_open) return;
    s_rings_open = true;
    const store_flash_t *flash = storage_store_flash();
    if (!flash) return;
    storage_store_lock();
    bool ok = store_ring_open(&s_events, flash, STORE_EVENTS_BASE, STORE_EVENTS_SECTORS) == ESP_OK &&
              store_ring_open(&s_metrics, flash, STORE_METRICS_BASE, STORE_METRICS_SECTORS) == ESP_OK;
    storage_store_unlock();
    s_persist = ok;
    if (!ok) ESP_LOGW(TAG, "history storage not usable");
}

static bool find_boot(const store_record_t *r, void *arg)
{
    if (r->type != HIST_EV_BOOT || r->len < 3) return true;
    *(uint16_t *)arg = get16(r->payload + 1);
    return false;
}

/* Starts the task when a feature is on; it stops itself when both are off. */
static esp_err_t apply_config(void)
{
    if (s_cfg.events || s_cfg.metrics) open_rings();   /* notifications alone never read the flash */
    bool accept = (s_cfg.events && s_persist) || s_sink;
    if (accept && !s_queue) {
        queued_t *area = heap_caps_malloc(QUEUE_LEN * sizeof(queued_t), MALLOC_CAP_SPIRAM);
        static StaticQueue_t queue_storage;
        if (area) s_queue = xQueueCreateStatic(QUEUE_LEN, sizeof(queued_t), (uint8_t *)area, &queue_storage);
    }
    if (s_cfg.metrics && !s_live) {
        s_live = heap_caps_calloc(LIVE_SAMPLES, sizeof *s_live, MALLOC_CAP_SPIRAM);
        s_live_head = s_live_count = 0;
        memset(&s_merge, 0, sizeof s_merge);
        s_have_traffic = false;
    }
    atomic_store_explicit(&s_events_on, accept && s_queue, memory_order_release);
    if ((s_cfg.events || s_cfg.metrics || s_sink) && !s_task &&
        xTaskCreate(history_task, "history", 3584, NULL, 2, &s_task) != pdPASS) {
        s_task = NULL;
        return ESP_ERR_NO_MEM;
    }
    return (s_cfg.metrics && !s_live) || (accept && !s_queue) ? ESP_ERR_NO_MEM : ESP_OK;
}

/* Boot number: the last boot record + 1 (events on and stored only). */
static void number_boot(void)
{
    if (s_boot || !s_persist) return;
    uint16_t last = 0;
    storage_store_lock();
    store_ring_walk(&s_events, find_boot, &last);
    storage_store_unlock();
    s_boot = (uint16_t)(last + 1);
}

static const char *const HISTORY_LEGACY[] = {"hist_ev", "hist_mx", "hist_snap"};
const nvs_flags_t history_flags = {.record = "hist_cfg", .legacy = HISTORY_LEGACY, .count = 3};

void history_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    uint8_t bits = nvs_flags_load(&history_flags);
    s_cfg.events = bits & 1; s_cfg.metrics = bits >> 1 & 1; s_cfg.snapshots = bits >> 2 & 1;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_inited = true;
    bool any = s_cfg.events || s_cfg.metrics || s_sink;
    if (any) {
        if (s_cfg.events || s_cfg.metrics) open_rings();   /* off: no flash read, no task, no buffer */
        if (s_cfg.events) number_boot();
    }
    esp_err_t err = any ? apply_config() : ESP_OK;
    bool accepting = atomic_load(&s_events_on);
    xSemaphoreGive(s_lock);
    if (err) ESP_LOGW(TAG, "history not fully started: %s", esp_err_to_name(err));
    if (!accepting) return;
    reset_history_entry_t entry = {0};
    bool have = reset_history_load(&entry, 1) == 1;
    const esp_app_desc_t *app = esp_app_get_description();
    const esp_partition_t *running = esp_ota_get_running_partition();
    const char *reason = have ? entry.reason : "?";
    /* FLASH/ROLLBACK are useful history labels but can override a physical
     * power-on. Select notification categories from the hardware reset cause. */
    esp_reset_reason_t raw = esp_reset_reason();
    bool bad = raw == ESP_RST_PANIC || raw == ESP_RST_INT_WDT || raw == ESP_RST_TASK_WDT ||
               raw == ESP_RST_WDT || raw == ESP_RST_BROWNOUT || !strcmp(reason, "PANIC") ||
               strstr(reason, "WDT") || !strcmp(reason, "BROWNOUT");
    const char *start = raw == ESP_RST_POWERON ? "Power-on start" : "Started";
    history_event(HIST_EV_BOOT, bad ? HIST_ERROR : HIST_INFO, "%s %s from %s, reset %s%s%s", start,
                  app->version, running ? running->label : "?", reason,
                  have && entry.who[0] ? ": " : "", have ? entry.who : "");
    esp_ota_img_states_t state;
    if (running && esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY)
        history_event(HIST_EV_UPDATE, HIST_INFO, "First start of %s after an update", app->version);
    if (have && entry.crash[0]) history_event(HIST_EV_CRASH, HIST_ERROR, "Crash: %.100s", entry.crash);
}

bool history_snapshots_before_update(void) {return s_cfg.snapshots;}

void history_get_config(bool *events, bool *metrics, bool *snapshots)
{
    *events = s_cfg.events; *metrics = s_cfg.metrics; *snapshots = s_cfg.snapshots;
}

esp_err_t history_set_config(bool events, bool metrics, bool snapshots)
{
    if (!s_lock) return ESP_ERR_INVALID_STATE;
    /* Persist before publishing the new state: one byte, all or nothing. */
    esp_err_t err = nvs_flags_save(&history_flags, (uint8_t)(events | metrics << 1 | snapshots << 2));
    if (err) return err;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool events_were = s_cfg.events;
    s_cfg.events = events; s_cfg.metrics = metrics; s_cfg.snapshots = snapshots;
    open_rings();
    if (events) number_boot();
    err = apply_config();
    xSemaphoreGive(s_lock);
    if (events && !events_were) history_event(HIST_EV_SETTINGS, HIST_INFO, "Event history switched on");
    return err;
}

void history_set_sink(history_sink_t sink)
{
    history_set_sink_poller(sink, NULL);
}

void history_set_sink_poller(history_sink_t sink, history_sink_poll_t poll)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_sink = sink;
    s_sink_poll = sink ? poll : NULL;
    /* Before history_init only the sink is noted; init applies it. */
    esp_err_t err = s_inited ? apply_config() : ESP_OK;
    xSemaphoreGive(s_lock);
    if (err) ESP_LOGW(TAG, "notification events not fully started: %s", esp_err_to_name(err));
}

/* --- jobs on an internal-RAM stack --- */
typedef struct {esp_err_t (*fn)(void *); void *arg; esp_err_t result; SemaphoreHandle_t done;} job_t;

static void job_task(void *arg)
{
    job_t *job = arg;
    job->result = job->fn(job->arg);
    xSemaphoreGive(job->done);
    vTaskDelete(NULL);
}

esp_err_t history_run_job(esp_err_t (*fn)(void *), void *arg)
{
    if (!fn) return ESP_ERR_INVALID_ARG;
    StaticSemaphore_t storage;
    job_t job = {.fn = fn, .arg = arg, .result = ESP_FAIL, .done = xSemaphoreCreateBinaryStatic(&storage)};
    /* A short-lived worker: nothing stays allocated between jobs. */
    if (xTaskCreate(job_task, "store_job", 4096, &job, 3, NULL) != pdPASS) return ESP_ERR_NO_MEM;
    xSemaphoreTake(job.done, portMAX_DELAY);
    vSemaphoreDelete(job.done);
    return job.result;
}

/* --- HTTP --- */
static bool query_value(httpd_req_t *req, const char *key, char *out, size_t cap)
{
    char query[96];
    return httpd_req_get_url_query_str(req, query, sizeof query) == ESP_OK &&
           httpd_query_key_value(query, key, out, cap) == ESP_OK;
}

typedef struct {char *buf; size_t cap, len; unsigned count, limit;} out_t;

static void out_add(out_t *o, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void out_add(out_t *o, const char *fmt, ...)
{
    if (o->len >= o->cap) return;
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(o->buf + o->len, o->cap - o->len, fmt, ap);
    va_end(ap);
    o->len = n < 0 || (size_t)n >= o->cap - o->len ? o->cap : o->len + (size_t)n;
}

static bool add_event(const store_record_t *r, void *arg)
{
    out_t *o = arg;
    if (r->len < 3 || r->type == 0 || r->type >= HIST_EV_KIND_END) return true;
    char text[HIST_TEXT_MAX + 1], escaped[HIST_TEXT_MAX * 2 + 1];
    size_t n = r->len - 3 > HIST_TEXT_MAX ? HIST_TEXT_MAX : r->len - 3u;
    memcpy(text, r->payload + 3, n); text[n] = 0;
    history_json_escape(escaped, sizeof escaped, text);
    out_add(o, "%s{\"k\":\"%s\",\"l\":\"%s\",\"b\":%u,\"t\":%lu,\"u\":%lu,\"m\":\"%s\"}", o->count ? "," : "",
            history_kind_name(r->type), history_level_name(r->payload[0]), (unsigned)get16(r->payload + 1),
            (unsigned long)r->wall, (unsigned long)r->uptime, escaped);
    return ++o->count < o->limit && o->len + 400 < o->cap;
}

static esp_err_t send_json(httpd_req_t *req, out_t *o)
{
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    if (o->len >= o->cap) {free(o->buf); httpd_resp_send_500(req); return ESP_FAIL;}
    esp_err_t err = httpd_resp_send(req, o->buf, (ssize_t)o->len);
    free(o->buf);
    return err;
}

static void add_config(out_t *o)
{
    out_add(o, "\"config\":{\"events\":%s,\"metrics\":%s,\"snapshots\":%s},\"persist\":%s,\"storage\":%s,\"boot\":%u,\"now\":%lu,\"uptime\":%lu",
            s_cfg.events ? "true" : "false", s_cfg.metrics ? "true" : "false", s_cfg.snapshots ? "true" : "false",
            s_persist ? "true" : "false", storage_store_available() ? "true" : "false", (unsigned)s_boot,
            (unsigned long)wall_now(), (unsigned long)uptime_s());
}

static esp_err_t get_events(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char value[8];
    unsigned limit = query_value(req, "limit", value, sizeof value) ? (unsigned)atoi(value) : 50;
    if (!limit || limit > 200) limit = 200;
    out_t o = {.cap = 8192 + limit * 300, .limit = limit};
    o.buf = heap_caps_malloc(o.cap, MALLOC_CAP_SPIRAM);
    if (!o.buf) {httpd_resp_send_500(req); return ESP_FAIL;}
    out_add(&o, "{");
    add_config(&o);
    out_add(&o, ",\"events\":[");
    if (s_persist) {
        storage_store_lock();
        store_ring_walk(&s_events, add_event, &o);
        storage_store_unlock();
    }
    out_add(&o, "]}");
    return send_json(req, &o);
}

static void add_point(out_t *o, const history_sample_t *s)
{
    out_add(o, "%s[%lu,%u,%lu,%lu,%lu,%lu,%lu,%lu,%d,%d,%u,%u]", o->count++ ? "," : "",
            (unsigned long)s->wall, (unsigned)s->boot, (unsigned long)s->uptime, (unsigned long)s->int_free,
            (unsigned long)s->int_largest, (unsigned long)s->psram_free, (unsigned long)s->rx, (unsigned long)s->tx,
            s->rssi, s->cpu == 0xFF ? -1 : s->cpu, s->peers, s->flags);
}

#define BUCKETS 288
typedef struct {history_agg_t *bucket; uint32_t range, step, now_wall, now_up; unsigned seen;} range_t;

static bool add_to_bucket(const store_record_t *r, void *arg)
{
    range_t *g = arg;
    history_sample_t s;
    uint32_t age;
    if (r->type != MX_TYPE || !history_sample_unpack(r->payload, r->len, r->wall, r->uptime, &s)) return true;
    if (!history_point_age(g->now_wall, g->now_up, s_boot, s.wall, s.uptime, s.boot, &age)) return ++g->seen < 8000;
    if (age < g->range && age / g->step < BUCKETS) history_agg_add(&g->bucket[age / g->step], &s);
    /* Clock-stamped points are in order: far past the range, stop. */
    return ++g->seen < 8000 && !(s.wall && age > g->range + 86400u);
}

static esp_err_t get_history(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char range[8] = "live";
    query_value(req, "range", range, sizeof range);
    uint32_t span = !strcmp(range, "day") ? 86400u : !strcmp(range, "week") ? 7 * 86400u : !strcmp(range, "month") ? 30 * 86400u : 0;
    out_t o = {.cap = 40 * 1024};
    o.buf = heap_caps_malloc(o.cap, MALLOC_CAP_SPIRAM);
    if (!o.buf) {httpd_resp_send_500(req); return ESP_FAIL;}
    out_add(&o, "{");
    add_config(&o);
    out_add(&o, ",\"range\":\"%s\",\"step\":%lu,\"fields\":[\"t\",\"b\",\"u\",\"int_free\",\"int_largest\",\"psram_free\",\"rx\",\"tx\",\"rssi\",\"cpu\",\"peers\",\"flags\"],\"points\":[",
            span ? range : "live", (unsigned long)(span ? (span / BUCKETS < 600 ? 600 : span / BUCKETS) : SAMPLE_PERIOD));
    if (!span) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        for (unsigned i = 0; s_live && i < s_live_count; i++)     /* newest first */
            add_point(&o, &s_live[(s_live_head + LIVE_SAMPLES - 1 - i) % LIVE_SAMPLES]);
        xSemaphoreGive(s_lock);
    } else if (s_persist) {
        range_t g = {.range = span, .step = span / BUCKETS < 600 ? 600 : span / BUCKETS, .now_wall = wall_now(), .now_up = uptime_s()};
        g.bucket = heap_caps_calloc(BUCKETS, sizeof *g.bucket, MALLOC_CAP_SPIRAM);
        if (g.bucket) {
            storage_store_lock();
            store_ring_walk(&s_metrics, add_to_bucket, &g);
            storage_store_unlock();
            for (unsigned i = 0; i < BUCKETS; i++) {
                history_sample_t s;
                if (history_agg_result(&g.bucket[i], &s)) add_point(&o, &s);
            }
            free(g.bucket);
        }
    }
    out_add(&o, "]}");
    return send_json(req, &o);
}

static esp_err_t post_config(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[128];
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body size"); return ESP_FAIL;}
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) {httpd_resp_send_408(req); return ESP_FAIL;}
        received += n;
    }
    body[received] = 0;
    cJSON *root = json_guard_parse(body);
    hist_config_t next = s_cfg;
    static const char *const keys[] = {"events", "metrics", "snapshots"};
    bool *fields[] = {&next.events, &next.metrics, &next.snapshots};
    bool valid = cJSON_IsObject(root), any = false;
    for (unsigned i = 0; valid && i < 3; i++) {
        const cJSON *item = cJSON_GetObjectItemCaseSensitive(root, keys[i]);
        if (!item) continue;
        if (!cJSON_IsBool(item)) valid = false;
        else {*fields[i] = cJSON_IsTrue(item); any = true;}
    }
    cJSON_Delete(root);
    if (!valid || !any) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "expected boolean events, metrics or snapshots"); return ESP_FAIL;}
    esp_err_t err = history_set_config(next.events, next.metrics, next.snapshots);
    if (err && err != ESP_ERR_NO_MEM) {httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err)); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    char response[96];
    snprintf(response, sizeof response, "{\"ok\":%s,\"persist\":%s%s}", err ? "false" : "true",
             s_persist ? "true" : "false", err ? ",\"reason\":\"not enough memory\"" : "");
    return httpd_resp_sendstr(req, response);
}

esp_err_t history_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/events", .method = HTTP_GET, .handler = get_events},
        {.uri = "/api/history", .method = HTTP_GET, .handler = get_history},
        {.uri = "/api/history/config", .method = HTTP_POST, .handler = post_config}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
