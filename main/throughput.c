/* Throughput test; see throughput.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "throughput.h"
#include <stdio.h>
#include <string.h>

/* --- throughput core (begin) --- */
#define THR_MEMORY_FLOOR 12288u   /* stop below this much free internal RAM */

static bool fail(char *why, size_t cap, const char *text)
{
    if (why && cap) snprintf(why, cap, "%s", text);
    return false;
}

bool throughput_url_valid(const char *url, char *why, size_t cap)
{
    if (!url) return fail(why, cap, "enter a URL");
    size_t n = strlen(url), skip = !strncmp(url, "https://", 8) ? 8 : !strncmp(url, "http://", 7) ? 7 : 0;
    if (!skip) return fail(why, cap, "the URL must start with http:// or https://");
    if (n > 240) return fail(why, cap, "the URL is too long");
    for (size_t i = 0; i < n; i++)
        if ((unsigned char)url[i] <= 0x20 || (unsigned char)url[i] >= 0x7F || url[i] == '"' || url[i] == '\\')
            return fail(why, cap, "the URL contains spaces or characters that are not allowed");
    const char *host = url + skip, *end = host;
    while (*end && *end != '/' && *end != '?' && *end != ':' && *end != '#') end++;
    if (end == host) return fail(why, cap, "the URL needs a host");
    for (const char *p = host; p < end; p++) if (*p == '@') return fail(why, cap, "credentials before the host are not supported");
    if (*end == ':') {
        unsigned port = 0;
        const char *p = end + 1;
        while (*p >= '0' && *p <= '9' && port <= 65535) port = port * 10 + (unsigned)(*p++ - '0');
        if (!port || port > 65535 || (*p && *p != '/' && *p != '?')) return fail(why, cap, "invalid port");
    }
    return true;
}

uint32_t throughput_kbps(uint64_t bytes, uint64_t us)
{
    if (!bytes || !us) return 0;
    while (us > (1ull << 40)) {us >>= 10; bytes >>= 10;}   /* keep rest * 8000 in range */
    if (!us) return 0;
    uint64_t whole = bytes / us, rest = bytes % us;        /* bytes per us, then kbit/s */
    if (whole > UINT32_MAX / 8000u) return UINT32_MAX;
    uint64_t kbps = whole * 8000u + (rest * 8000u + us / 2) / us;
    return kbps > UINT32_MAX ? UINT32_MAX : (uint32_t)kbps;
}

const char *throughput_stop(uint64_t bytes, uint64_t us, uint32_t seconds, size_t internal_free)
{
    if (internal_free < THR_MEMORY_FLOOR) return "stopped early: internal memory low";
    if (bytes >= THR_MAX_BYTES) return "size limit reached";
    if (us >= (uint64_t)seconds * 1000000u) return "time limit reached";
    return NULL;
}
/* --- throughput core (end) --- */

#ifdef ESP_PLATFORM
#include "history.h"
#include "json_guard.h"
#include "task_reaper.h"
#include "web_ui.h"
#include "esp_attr.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <stdlib.h>

typedef struct {
    bool running;
    char url[244];
    uint32_t seconds;
    uint64_t bytes, elapsed_us, first_byte_us;
    int status;
    char result[96];
} job_t;
EXT_RAM_BSS_ATTR static job_t s_job;            /* PSRAM: no internal RAM between tests */
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

static void worker(void *arg)
{
    (void)arg;
    char *buffer = heap_caps_malloc(4096, MALLOC_CAP_SPIRAM);
    esp_http_client_config_t hc = {.url = s_job.url, .timeout_ms = 10000, .buffer_size = 4096,
                                   .crt_bundle_attach = esp_crt_bundle_attach, .max_redirection_count = 3};
    esp_http_client_handle_t client = buffer ? esp_http_client_init(&hc) : NULL;
    const char *why = !buffer || !client ? "out of memory" : NULL;
    int64_t start = esp_timer_get_time(), body_start = 0;
    uint64_t bytes = 0;
    int status = 0;
    if (client && esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0) {
        status = esp_http_client_get_status_code(client);
        body_start = esp_timer_get_time();
        if (status < 200 || status >= 300) why = "the server did not return the file";
        while (!why) {
            int n = esp_http_client_read(client, buffer, 4096);
            int64_t now = esp_timer_get_time();
            if (n < 0) {why = "connection lost"; break;}
            if (n == 0) {why = esp_http_client_is_complete_data_received(client) ? "file complete" : "connection closed"; break;}
            bytes += (uint64_t)n;
            taskENTER_CRITICAL(&s_mux);
            s_job.bytes = bytes; s_job.elapsed_us = (uint64_t)(now - body_start); s_job.status = status;
            taskEXIT_CRITICAL(&s_mux);
            why = throughput_stop(bytes, (uint64_t)(now - body_start), s_job.seconds, heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        }
    } else if (!why) why = "cannot connect (check the URL, DNS and the certificate)";
    int64_t end = esp_timer_get_time();
    if (client) esp_http_client_cleanup(client);
    free(buffer);
    uint64_t elapsed = body_start ? (uint64_t)(end - body_start) : 0;
    uint32_t kbps = throughput_kbps(bytes, elapsed);
    taskENTER_CRITICAL(&s_mux);
    s_job.bytes = bytes; s_job.elapsed_us = elapsed; s_job.status = status;
    s_job.first_byte_us = body_start ? (uint64_t)(body_start - start) : 0;
    snprintf(s_job.result, sizeof s_job.result, "%s", why);
    s_job.running = false;
    taskEXIT_CRITICAL(&s_mux);
    if (bytes) history_event(HIST_EV_UPLINK, HIST_INFO, "Throughput test: %lu.%02lu Mbit/s over %lu KB",
                             (unsigned long)(kbps / 1000), (unsigned long)(kbps % 1000 / 10), (unsigned long)(bytes / 1024));
    task_reaper_self_delete();
}

static esp_err_t get_test(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    job_t j;
    taskENTER_CRITICAL(&s_mux);
    j.running = s_job.running; j.bytes = s_job.bytes; j.elapsed_us = s_job.elapsed_us; j.status = s_job.status;
    j.first_byte_us = s_job.first_byte_us;
    memcpy(j.result, s_job.result, sizeof j.result);
    taskEXIT_CRITICAL(&s_mux);
    char out[256];
    snprintf(out, sizeof out, "{\"running\":%s,\"bytes\":%llu,\"elapsed_ms\":%llu,\"kbps\":%lu,\"first_byte_ms\":%llu,\"http\":%d,\"result\":\"%s\"}",
             j.running ? "true" : "false", (unsigned long long)j.bytes, (unsigned long long)(j.elapsed_us / 1000),
             (unsigned long)throughput_kbps(j.bytes, j.elapsed_us), (unsigned long long)(j.first_byte_us / 1000), j.status, j.result);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, out);
}

static esp_err_t post_test(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[384], why[96] = "invalid request";
    int total = req->content_len, received = 0;
    bool ok = total > 0 && total < (int)sizeof body;
    while (ok && received < total) {int n = httpd_req_recv(req, body + received, total - received); if (n <= 0) ok = false; else received += n;}
    body[ok ? received : 0] = 0;
    cJSON *root = ok ? json_guard_parse(body) : NULL;
    const cJSON *url = cJSON_GetObjectItemCaseSensitive(root, "url"), *seconds = cJSON_GetObjectItemCaseSensitive(root, "seconds");
    ok = cJSON_IsObject(root) && cJSON_IsString(url) && throughput_url_valid(url->valuestring, why, sizeof why) &&
         (!seconds || (cJSON_IsNumber(seconds) && seconds->valuedouble >= 3 && seconds->valuedouble <= THR_MAX_S));
    bool started = false, busy = false;
    if (ok && heap_caps_get_free_size(MALLOC_CAP_INTERNAL) < 24576) {ok = false; snprintf(why, sizeof why, "not enough free memory right now");}
    if (ok) {
        taskENTER_CRITICAL(&s_mux);
        busy = s_job.running;
        if (!busy) {
            memset(&s_job, 0, sizeof s_job);
            snprintf(s_job.url, sizeof s_job.url, "%s", url->valuestring);
            s_job.seconds = seconds ? (uint32_t)seconds->valuedouble : 10;
            s_job.running = true;
        }
        taskEXIT_CRITICAL(&s_mux);
        if (!busy) {
            started = xTaskCreateWithCaps(worker, "speedtest", 8192, NULL, 3, NULL, MALLOC_CAP_SPIRAM) == pdPASS;
            if (!started) {taskENTER_CRITICAL(&s_mux); s_job.running = false; taskEXIT_CRITICAL(&s_mux); snprintf(why, sizeof why, "out of memory");}
        }
    }
    cJSON_Delete(root);
    httpd_resp_set_type(req, "application/json");
    if (busy) {httpd_resp_set_status(req, "409 Conflict"); return httpd_resp_sendstr(req, "{\"ok\":false,\"error\":\"a test is already running\"}");}
    if (!started) {
        httpd_resp_set_status(req, ok ? "503 Service Unavailable" : "400 Bad Request");
        char out[160];
        snprintf(out, sizeof out, "{\"ok\":false,\"error\":\"%s\"}", why);
        return httpd_resp_sendstr(req, out);
    }
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

/* Zero bytes to the browser, which measures the link to the gateway. */
static esp_err_t get_blob(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char query[32], value[12];
    uint32_t bytes = 4u * 1024u * 1024u;
    if (httpd_req_get_url_query_str(req, query, sizeof query) == ESP_OK && httpd_query_key_value(query, "bytes", value, sizeof value) == ESP_OK)
        bytes = (uint32_t)strtoul(value, NULL, 10);
    if (bytes < 65536 || bytes > THR_BLOB_MAX) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "bytes must be 65536-16777216"); return ESP_FAIL;}
    char *chunk = heap_caps_calloc(1, 4096, MALLOC_CAP_SPIRAM);
    if (!chunk) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/octet-stream");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = ESP_OK;
    for (uint32_t sent = 0; sent < bytes && err == ESP_OK; sent += 4096)
        err = httpd_resp_send_chunk(req, chunk, (ssize_t)(bytes - sent < 4096 ? bytes - sent : 4096));
    if (err == ESP_OK) err = httpd_resp_send_chunk(req, NULL, 0);
    free(chunk);
    return err;
}

esp_err_t throughput_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/diag/speedtest", .method = HTTP_GET, .handler = get_test},
        {.uri = "/api/diag/speedtest", .method = HTTP_POST, .handler = post_test},
        {.uri = "/api/diag/speedtest/blob", .method = HTTP_GET, .handler = get_blob}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
