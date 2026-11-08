/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Remote commands over the Telegram bot: see telegram_commands.h.
 * Original implementation, Mattboxx Edition. MIT. */
#include "telegram_commands.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "json_guard.h"

#define TG_MAX_AGE_S 600

bool tg_command_normalize(const char *in, char *out, size_t cap)
{
    if (!in || !out || !cap) return false;
    while (*in && isspace((unsigned char)*in)) in++;
    if (*in == '/') in++;                                   /* bot command form */
    size_t n = 0;
    const char *p = in;
    /* first word, without a "@BotName" suffix */
    while (*p && !isspace((unsigned char)*p) && *p != '@') {
        if (n + 1 >= cap) return false;
        out[n++] = *p++;
    }
    if (*p == '@') while (*p && !isspace((unsigned char)*p)) p++;
    size_t rest = strlen(p);
    if (n + rest + 1 > cap) return false;
    memcpy(out + n, p, rest + 1);
    return n > 0;
}

void tg_updates_parse(const char *json, size_t len, const char *chat, uint32_t now_wall, tg_updates_t *out)
{
    memset(out, 0, sizeof *out);
    if (!json || !len || !chat || !chat[0]) return;
    cJSON *root = json_guard_preflight(json, len) ? cJSON_ParseWithLength(json, len) : NULL;
    const cJSON *ok = root ? cJSON_GetObjectItemCaseSensitive(root, "ok") : NULL;
    const cJSON *result = root ? cJSON_GetObjectItemCaseSensitive(root, "result") : NULL;
    if (!cJSON_IsTrue(ok) || !cJSON_IsArray(result)) {
        cJSON_Delete(root);
        return;
    }
    out->valid = true;
    const cJSON *update;
    cJSON_ArrayForEach(update, result) {
        const cJSON *id = cJSON_GetObjectItemCaseSensitive(update, "update_id");
        if (!cJSON_IsNumber(id) || id->valuedouble < 1 || id->valuedouble > 4294967295.0) continue;
        uint32_t uid = (uint32_t)id->valuedouble;
        if (uid > out->last_update_id) out->last_update_id = uid;
        const cJSON *msg = cJSON_GetObjectItemCaseSensitive(update, "message");
        const cJSON *from_chat = msg ? cJSON_GetObjectItemCaseSensitive(msg, "chat") : NULL;
        const cJSON *cid = from_chat ? cJSON_GetObjectItemCaseSensitive(from_chat, "id") : NULL;
        const cJSON *text = msg ? cJSON_GetObjectItemCaseSensitive(msg, "text") : NULL;
        const cJSON *date = msg ? cJSON_GetObjectItemCaseSensitive(msg, "date") : NULL;
        if (!cJSON_IsNumber(cid) || !cJSON_IsString(text)) continue;   /* not a text message */
        char id_text[24];
        snprintf(id_text, sizeof id_text, "%.0f", cid->valuedouble);
        if (strcmp(id_text, chat) != 0) { out->other_chats++; continue; }
        if (now_wall && cJSON_IsNumber(date) && (date->valuedouble + TG_MAX_AGE_S < (double)now_wall)) { out->stale++; continue; }
        if (out->count >= (int)(sizeof out->cmd / sizeof out->cmd[0])) continue;
        if (tg_command_normalize(text->valuestring, out->cmd[out->count].text, TG_CMD_TEXT_MAX)) out->count++;
    }
    cJSON_Delete(root);
}

bool telegram_commands_config_valid(const telegram_commands_config_t *c)
{
    return c && c->poll_interval_seconds >= 5 && c->poll_interval_seconds <= 300;
}

#ifndef TG_COMMANDS_HOST_TEST
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "ml_tls_distrust.h"
#include "notify_channels.h"
#include "nvs_params.h"
#include "remote_commands.h"
#include "tailscale_config.h"
#include "task_reaper.h"
#include <time.h>

static const char *TAG = "tg_cmd";
#define TG_ANSWER_MAX 32768
#define TG_STACK 10240

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static telegram_commands_config_t s_cfg;
static telegram_commands_status_t s_st;
static TaskHandle_t s_task;
static uint32_t s_last_update;      /* RAM only: a restart skips the backlog */
static bool s_have_offset;

static void defaults(telegram_commands_config_t *c)
{
    memset(c, 0, sizeof *c);
    c->commands_only_when_tailscale_down = true;
    c->info_enabled = true;
    c->poll_interval_seconds = 15;
}

static void load(telegram_commands_config_t *c)
{
    defaults(c);
    uint8_t f = 0;
    uint16_t poll = 0;
    if (nvs_param_get_u8("tg_cflags", &f) == ESP_OK) {
        c->commands_enabled = f & 1;
        c->commands_only_when_tailscale_down = (f & 2) != 0;
        c->allow_direct_mac = (f & 4) != 0;
        c->info_enabled = (f & 8) != 0;
        c->info_include_details = (f & 16) != 0;
    }
    if (nvs_param_get_u16("tg_cpoll", &poll) == ESP_OK && poll >= 5 && poll <= 300) c->poll_interval_seconds = poll;
}

static uint32_t wall(void) { time_t t = time(NULL); return t > 1700000000 ? (uint32_t)t : 0; }

static bool uplink_up(void)
{
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    return sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr;
}

static void set_error(const char *why)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    strlcpy(s_st.last_error, why ? why : "", sizeof s_st.last_error);
    xSemaphoreGive(s_lock);
}

/* GET getUpdates; the token is wiped from the URL buffer once used. */
static int fetch(const char *token, const char *query, char *answer, size_t cap)
{
    char url[200];
    int n = snprintf(url, sizeof url, "https://api.telegram.org/bot%s/getUpdates?%s", token, query);
    if (n <= 0 || (size_t)n >= sizeof url) { memset(url, 0, sizeof url); return -1; }
    esp_http_client_config_t hc = {.url = url, .method = HTTP_METHOD_GET, .timeout_ms = 15000,
                                   .crt_bundle_attach = ml_tls_bundle_attach, .disable_auto_redirect = true};
    esp_http_client_handle_t client = esp_http_client_init(&hc);
    memset(url, 0, sizeof url);
    if (!client) return -1;
    int total = -1;
    if (esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0
        && esp_http_client_get_status_code(client) == 200) {
        total = 0;
        while ((size_t)total < cap - 1) {
            int got = esp_http_client_read(client, answer + total, (int)(cap - 1 - (size_t)total));
            if (got <= 0) break;
            total += got;
        }
        answer[total] = 0;
        if ((size_t)total >= cap - 1) total = -1;   /* larger than allowed: refuse */
    }
    esp_http_client_cleanup(client);
    return total;
}

static void reply(const char *text)
{
    char why[80] = "";
    if (notify_telegram_send_text(text, why, sizeof why) != ESP_OK) set_error(why);
}

static void send_info(const telegram_commands_config_t *c)
{
    char *text = remote_info_text(c->info_include_details, false);
    if (!text) { reply("info: not enough memory"); return; }
    /* Telegram notification bodies are bounded: send line-aligned parts. */
    size_t len = strlen(text), off = 0;
    while (off < len) {
        size_t take = len - off > 900 ? 900 : len - off;
        if (off + take < len) { size_t cut = take; while (cut > 200 && text[off + cut - 1] != '\n') cut--; if (cut > 200) take = cut; }
        char saved = text[off + take];
        text[off + take] = 0;
        reply(text + off);
        text[off + take] = saved;
        off += take;
    }
    free(text);
}

static void run(const telegram_commands_config_t *c, const char *command)
{
    char text[160];
    const char *title = NULL;
    remote_cmd_kind_t kind = remote_command_run(command, c->info_enabled, c->allow_direct_mac, text, sizeof text, &title);
    if (kind == REMOTE_CMD_NONE) return;
    if (kind == REMOTE_CMD_INFO) send_info(c);
    else if (text[0]) reply(text);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (kind == REMOTE_CMD_ERROR) s_st.command_errors++;
    else s_st.commands_received++;
    xSemaphoreGive(s_lock);
}

static void poll_once(const telegram_commands_config_t *c, const char *token, const char *chat)
{
    char *answer = heap_caps_malloc(TG_ANSWER_MAX, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!answer) { set_error("not enough memory"); return; }
    tg_updates_t u;
    char query[96];
    if (!s_have_offset) {
        /* First poll: skip everything sent before (never run old commands). */
        int n = fetch(token, "offset=-1&limit=1&timeout=0", answer, TG_ANSWER_MAX);
        if (n > 0) {
            tg_updates_parse(answer, (size_t)n, chat, 0, &u);
            if (u.valid) { s_last_update = u.last_update_id; s_have_offset = true; set_error(""); }
            else set_error("unexpected answer from Telegram");
        } else set_error("cannot reach api.telegram.org");
        free(answer);
        return;
    }
    for (int attempt = 0; attempt < 2; attempt++) {
        snprintf(query, sizeof query, "offset=%lu&limit=%d&timeout=0",
                 (unsigned long)s_last_update + 1, attempt ? 1 : 5);
        int n = fetch(token, query, answer, TG_ANSWER_MAX);
        if (n <= 0) { set_error("cannot reach api.telegram.org"); break; }
        tg_updates_parse(answer, (size_t)n, chat, wall(), &u);
        if (!u.valid && attempt == 0) continue;      /* retry one update at a time */
        if (!u.valid) {
            /* One update this firmware cannot read: skip it by its id. */
            const char *p = strstr(answer, "\"update_id\":");
            unsigned long id = p ? strtoul(p + 12, NULL, 10) : 0;
            if (id > s_last_update) s_last_update = (uint32_t)id;
            set_error("skipped an unreadable update");
            break;
        }
        if (u.last_update_id > s_last_update) s_last_update = u.last_update_id;   /* before running */
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_st.skipped_other_chats += (uint32_t)u.other_chats;
        s_st.last_error[0] = 0;
        xSemaphoreGive(s_lock);
        for (int i = 0; i < u.count; i++) run(c, u.cmd[i].text);
        break;
    }
    free(answer);
}

static void task_main(void *arg)
{
    (void)arg;
    for (;;) {
        telegram_commands_config_t c;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        c = s_cfg;
        xSemaphoreGive(s_lock);
        char token[96], chat[40];
        bool target = notify_telegram_target(token, sizeof token, chat, sizeof chat);
        if (!c.commands_enabled || !target) {
            memset(token, 0, sizeof token);
            break;
        }
        bool due = !c.commands_only_when_tailscale_down || (tailscale_enabled && !tailscale_is_connected());
        if (due && uplink_up()) poll_once(&c, token, chat);
        memset(token, 0, sizeof token);
        (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000u * c.poll_interval_seconds));
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_task = NULL;
    s_st.running = false;
    s_have_offset = false;
    xSemaphoreGive(s_lock);
    task_reaper_self_delete();
}

/* Caller holds s_lock. */
static void start_or_wake_locked(void)
{
    char token[96], chat[40];
    bool target = notify_telegram_target(token, sizeof token, chat, sizeof chat);
    memset(token, 0, sizeof token);
    if (!s_cfg.commands_enabled || !target) {
        if (s_task) xTaskNotifyGive(s_task);          /* it sees the change and exits */
        return;
    }
    if (s_task) { xTaskNotifyGive(s_task); return; }
    s_st.running = xTaskCreateWithCaps(task_main, "tg_cmd", TG_STACK, NULL, 2, &s_task, MALLOC_CAP_SPIRAM) == pdPASS;
    if (!s_st.running) { s_task = NULL; ESP_LOGW(TAG, "Cannot start the Telegram command task"); }
}

void telegram_commands_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    load(&s_cfg);
    start_or_wake_locked();
    xSemaphoreGive(s_lock);
}

void telegram_commands_refresh(void)
{
    if (!s_lock) return;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    start_or_wake_locked();
    xSemaphoreGive(s_lock);
}

void telegram_commands_get_config(telegram_commands_config_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_cfg;
    xSemaphoreGive(s_lock);
}

void telegram_commands_get_status(telegram_commands_status_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_st;
    out->running = s_task != NULL;
    xSemaphoreGive(s_lock);
}

esp_err_t telegram_commands_set_config(const telegram_commands_config_t *c)
{
    if (!telegram_commands_config_valid(c)) return ESP_ERR_INVALID_ARG;
    uint8_t f = (c->commands_enabled ? 1 : 0) | (c->commands_only_when_tailscale_down ? 2 : 0) |
                (c->allow_direct_mac ? 4 : 0) | (c->info_enabled ? 8 : 0) | (c->info_include_details ? 16 : 0);
    esp_err_t err = nvs_param_set_u8("tg_cflags", f);
    if (err == ESP_OK) err = nvs_param_set_u16("tg_cpoll", c->poll_interval_seconds);
    if (err != ESP_OK) return err;                     /* persisted before it applies */
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_cfg = *c;
    start_or_wake_locked();
    xSemaphoreGive(s_lock);
    return ESP_OK;
}
#endif
