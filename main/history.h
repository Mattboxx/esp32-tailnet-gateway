/* Persistent event history and resource/traffic history (3.x storage).
 *
 * Events: boot, crash, update, uplink and tailnet changes, settings copies,
 * security-relevant actions. history_event() never touches flash: it queues
 * the line (dropped and counted when the queue is full) and the history task
 * writes it, at most HIST_RATE_BURST lines a minute (the rest are counted).
 *
 * Metrics: one sample a minute (internal/PSRAM heap, uplink traffic, RSSI,
 * CPU, temperature, online peers) kept 6 h in PSRAM; every 10 samples are
 * merged into one record of the metrics ring (~45 days of 10-minute points).
 *
 * Everything starts off. Off, there is no task, no buffer, no flash write
 * and history_event() returns at once; the task and its PSRAM buffers exist
 * only while events or metrics are on. Without the storage partition (2.x layout) events are not kept and only
 * the 6-hour metrics exist.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"

typedef enum {
    HIST_EV_BOOT = 1, HIST_EV_CRASH, HIST_EV_UPDATE, HIST_EV_UPLINK, HIST_EV_TAILNET,
    HIST_EV_SETTINGS, HIST_EV_SECURITY, HIST_EV_STORAGE, HIST_EV_SERVICE, HIST_EV_KIND_END
} history_kind_t;
typedef enum {HIST_INFO, HIST_WARN, HIST_ERROR} history_level_t;

#define HIST_TEXT_MAX 160
#define HIST_RATE_BURST 20       /* lines; refilled one every 3 s */
#define HIST_SAMPLE_BYTES 28
#define HIST_UP_UPLINK 0x01
#define HIST_UP_TAILNET 0x02

typedef struct {
    uint32_t uptime, wall;       /* end of the interval; wall 0 when the clock was not set */
    uint16_t boot;
    uint32_t int_free, int_largest, psram_free;   /* bytes, lowest in the interval */
    uint32_t rx, tx;             /* uplink bytes during the interval */
    int8_t rssi;                 /* dBm average, 0 = no Wi-Fi uplink */
    uint8_t cpu;                 /* % average, 0xFF unknown */
    uint8_t peers;               /* most online tailnet peers */
    uint8_t flags;               /* HIST_UP_* held for the whole interval */
    int16_t temp;                /* 0.1 degC average, INT16_MIN unknown */
} history_sample_t;

typedef struct {
    history_sample_t s;
    uint32_t count;
    int32_t rssi_sum; uint32_t rssi_n;
    uint32_t cpu_sum, cpu_n;
    int32_t temp_sum; uint32_t temp_n;
} history_agg_t;

typedef struct {uint32_t tokens, last; bool started;} history_rate_t;

/* Core (pure, host-tested). */
void history_sample_pack(const history_sample_t *s, uint8_t out[HIST_SAMPLE_BYTES]);
bool history_sample_unpack(const uint8_t *in, size_t len, uint32_t wall, uint32_t uptime, history_sample_t *out);
void history_agg_add(history_agg_t *agg, const history_sample_t *s);
bool history_agg_result(const history_agg_t *agg, history_sample_t *out);
bool history_rate_allow(history_rate_t *rate, uint32_t now_s);
size_t history_json_escape(char *out, size_t cap, const char *in);
const char *history_kind_name(unsigned kind);
const char *history_level_name(unsigned level);
/* Age in seconds of a point for the long ranges; false when it cannot be
 * placed (no clock and another boot). */
bool history_point_age(uint32_t now_wall, uint32_t now_up, uint16_t now_boot,
                       uint32_t wall, uint32_t up, uint16_t boot, uint32_t *age);

/* Firmware. */
/* After NVS. Off (the default) it reads one setting and returns: no task,
 * buffer or flash access. */
void history_init(void);
bool history_snapshots_before_update(void);   /* setting: settings copy before updates */
void history_get_config(bool *events, bool *metrics, bool *snapshots);
/* Persist, then apply (same path as POST /api/history/config). */
esp_err_t history_set_config(bool events, bool metrics, bool snapshots);
/* NVS record of the three switches (events bit 0, metrics 1, snapshots 2). */
#include "nvs_flags.h"
extern const nvs_flags_t history_flags;
void history_event(history_kind_t kind, history_level_t level, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));
/* Run fn(arg) on a short-lived internal-RAM-stack task and wait for it
 * (callable from any stack; flash access needs an internal one). */
esp_err_t history_run_job(esp_err_t (*fn)(void *arg), void *arg);
uint16_t history_boot_number(void);
/* A consumer of every event line (notifications), called on the history
 * task. Setting one keeps the event bus running without the flash log. */
typedef void (*history_sink_t)(unsigned kind, unsigned level, uint32_t wall, const char *text);
void history_set_sink(history_sink_t sink);
/* Optional bounded housekeeping on the existing history task, after queued
 * events are drained. No additional task/timer is created. */
typedef void (*history_sink_poll_t)(void);
void history_set_sink_poller(history_sink_t sink, history_sink_poll_t poll);
esp_err_t history_register_http(httpd_handle_t server);
