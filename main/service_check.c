/* On-demand LAN -> Tailnet destination check; see service_check.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "service_check.h"
#include "service_lease.h"
#include "homelab_ops.h"
#include "tailscale_config.h"
#include "microlink.h"
#include "ml_policy.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nvs_params.h"
#include "ntfy_integration.h"
#include "mqtt_integration.h"
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>

typedef struct {bool ready, connected, authority; uint32_t resolved_ip;} sc_path_t;
/* Platform hooks; the core below is also compiled against host fixtures. */
static uint64_t sc_now_ms(void);
static bool sc_rule(int index, tailnet_forward_rule_t *rule);
static void sc_path(const tailnet_forward_rule_t *rule, sc_path_t *out);
static int sc_connect(uint32_t ip_hbo, uint16_t port, uint32_t timeout_ms);
static bool sc_admit(void);
static esp_err_t sc_start_worker(void);
static void sc_notify(int index, bool recovered);
#define SC_LOCK() xSemaphoreTake(sc_lock, portMAX_DELAY)
#define SC_UNLOCK() xSemaphoreGive(sc_lock)
static SemaphoreHandle_t sc_lock;

/* --- service check core (begin) --- */
static service_check_result_t sc_results[TAILNET_FORWARD_MAX];
static struct {bool active; int index; uint32_t token;} sc_pending;
static service_watch_config_t sc_watch = {.interval_s = 900};
static uint64_t sc_watch_next;
static int sc_watch_cursor;
static uint8_t sc_watch_fails[TAILNET_FORWARD_MAX];
static bool sc_watch_alerted[TAILNET_FORWARD_MAX];

static bool sc_watch_valid(const service_watch_config_t *c)
{
    return c && c->interval_s >= SERVICE_WATCH_MIN_S && c->interval_s <= SERVICE_WATCH_MAX_S;
}

/* Locked: when due, queue the next enabled TCP rule (manual requests win). */
static void sc_watch_schedule_locked(uint64_t now)
{
    if (!sc_watch.enabled || sc_pending.active || now < sc_watch_next) return;
    sc_watch_next = now + (uint64_t)sc_watch.interval_s * 1000u;
    for (int n = 0; n < TAILNET_FORWARD_MAX; n++) {
        int i = (sc_watch_cursor + n) % TAILNET_FORWARD_MAX;
        tailnet_forward_rule_t rule;
        if (!sc_rule(i, &rule) || !rule.enabled || rule.proto != TAILNET_FORWARD_PROTO_TCP) continue;
        uint32_t token = service_lease_token(&rule);
        sc_watch_cursor = (i + 1) % TAILNET_FORWARD_MAX;
        sc_pending.active = true; sc_pending.index = i; sc_pending.token = token;
        sc_results[i] = (service_check_result_t){.state = SC_PENDING, .token = token};
        return;
    }
}

/* Locked: 0 nothing, 1 newly unreachable, 2 recovered. Only handshake
 * outcomes count; tunnel/resource states are not evidence about the service. */
static int sc_watch_observe_locked(int index, uint8_t state)
{
    if (state == SC_REACHABLE) {
        sc_watch_fails[index] = 0;
        if (sc_watch_alerted[index]) {sc_watch_alerted[index] = false; return 2;}
    } else if (state == SC_NO_ANSWER) {
        if (sc_watch_fails[index] < UINT8_MAX) sc_watch_fails[index]++;
        if (sc_watch_fails[index] >= 2 && !sc_watch_alerted[index]) {sc_watch_alerted[index] = true; return 1;}
    }
    return 0;
}

static const char *const sc_names[SC_STATE_COUNT] = {
    "not_tested", "pending", "reachable", "no_tcp_answer", "udp_unverifiable", "control_offline",
    "policy_not_ready", "unresolved", "resource_deferred", "local_error", "rule_changed"};
static const char *const sc_summaries[SC_STATE_COUNT] = {
    "No destination check for this rule's current settings",
    "Destination check queued for the operations worker",
    "This gateway completed a TCP handshake with the Tailnet destination",
    "No TCP handshake within the time limit; refusal, filtering and timeout are not distinguished",
    "UDP has no handshake; the destination cannot be verified without an application reply",
    "Tailnet control connection is not available",
    "Current Tailnet policy authority is incomplete or suspended",
    "Destination did not resolve to a Tailnet IPv4 address from a literal or the peer cache",
    "Optional-work admission deferred the check",
    "Local socket setup failed",
    "The rule changed before the check ran; nothing was tested"};
static const char *const sc_steps[SC_STATE_COUNT] = {
    "Test the destination before enabling the rule",
    "Wait a few seconds, then refresh",
    "Enable the rule, then connect from an allowed LAN client; check the application itself",
    "Verify the peer is online, the service listens on that port and the Tailnet ACL allows this gateway",
    "Test with the real UDP client after enabling the rule and watch the accepted counter",
    "Check Tailscale login and uplink status",
    "Wait for a complete control map; the policy gate is never bypassed",
    "Use a current Tailnet IPv4 or a MagicDNS name of a known peer",
    "Inspect free heap, largest block and socket headroom, then retry",
    "Retry later; inspect socket usage if it persists",
    "Test again with the saved settings"};

const char *service_check_state_name(unsigned s) {return s < SC_STATE_COUNT ? sc_names[s] : "unknown";}
const char *service_check_summary(unsigned s) {return s < SC_STATE_COUNT ? sc_summaries[s] : "";}
const char *service_check_next_step(unsigned s) {return s < SC_STATE_COUNT ? sc_steps[s] : "";}

static esp_err_t sc_request_locked(int index, uint32_t expected, uint64_t now)
{
    tailnet_forward_rule_t rule;
    if (index < 0 || index >= TAILNET_FORWARD_MAX || !sc_rule(index, &rule)) return ESP_ERR_INVALID_ARG;
    if (!expected || service_lease_token(&rule) != expected) return ESP_ERR_INVALID_STATE;
    if (sc_pending.active) return ESP_ERR_NOT_FINISHED;
    const service_check_result_t *last = &sc_results[index];
    if (last->token == expected && last->observed_ms && now >= last->observed_ms
        && now - last->observed_ms < SERVICE_CHECK_COOLDOWN_MS) return ESP_ERR_TIMEOUT;
    sc_pending.active = true;
    sc_pending.index = index;
    sc_pending.token = expected;
    sc_results[index] = (service_check_result_t){.state = SC_PENDING, .token = expected};
    return ESP_OK;
}

static bool sc_get_locked(int index, uint32_t current, service_check_result_t *out)
{
    if (index < 0 || index >= TAILNET_FORWARD_MAX || !current || sc_results[index].token != current) return false;
    *out = sc_results[index];
    return out->state != SC_NONE;
}

/* Runs without the lock held around network I/O; publishes only if the
 * pending request is still the one it started. */
static void sc_run(void)
{
    SC_LOCK();
    sc_watch_schedule_locked(sc_now_ms());
    bool active = sc_pending.active;
    int index = sc_pending.index;
    uint32_t token = sc_pending.token;
    SC_UNLOCK();
    if (!active) return;
    service_check_result_t r = {.token = token};
    tailnet_forward_rule_t rule;
    uint64_t started = sc_now_ms();
    if (!sc_rule(index, &rule) || service_lease_token(&rule) != token) r.state = SC_CHANGED;
    else if (rule.proto == TAILNET_FORWARD_PROTO_UDP) r.state = SC_UDP_UNVERIFIABLE;
    else {
        sc_path_t path = {0};
        sc_path(&rule, &path);
        r.resolved_ip = path.resolved_ip;
        if (!path.connected) r.state = SC_NO_CONTROL;
        else if (!path.authority) r.state = SC_NO_AUTHORITY;
        else if ((path.resolved_ip & 0xffc00000u) != 0x64400000u) {r.state = SC_UNRESOLVED; r.resolved_ip = 0;}
        else if (!sc_admit()) r.state = SC_RESOURCE;
        else {
            int outcome = sc_connect(path.resolved_ip, rule.destination_port, SERVICE_CHECK_TIMEOUT_MS);
            r.state = outcome > 0 ? SC_REACHABLE : outcome == 0 ? SC_NO_ANSWER : SC_LOCAL_ERROR;
        }
    }
    r.observed_ms = sc_now_ms();
    if (!r.observed_ms) r.observed_ms = 1;
    r.latency_ms = (uint32_t)(r.observed_ms >= started ? r.observed_ms - started : 0);
    int event = 0;
    bool notify = false;
    SC_LOCK();
    if (sc_pending.active && sc_pending.index == index && sc_pending.token == token) {
        sc_results[index] = r;
        sc_pending.active = false;
        event = sc_watch_observe_locked(index, r.state);
        notify = sc_watch.enabled && sc_watch.notify;
    }
    SC_UNLOCK();
    if (event && notify) sc_notify(index, event == 2);
}
/* --- service check core (end) --- */

static void sc_init(void)
{
    static StaticSemaphore_t storage;
    static portMUX_TYPE init = portMUX_INITIALIZER_UNLOCKED;
    portENTER_CRITICAL(&init);
    if (!sc_lock) sc_lock = xSemaphoreCreateMutexStatic(&storage);
    portEXIT_CRITICAL(&init);
}

esp_err_t service_check_request(int index, uint32_t expected_token)
{
    sc_init();
    if (sc_start_worker() != ESP_OK) return ESP_ERR_NO_MEM;
    SC_LOCK();
    esp_err_t err = sc_request_locked(index, expected_token, sc_now_ms());
    SC_UNLOCK();
    return err;
}

bool service_check_get(int index, uint32_t current_token, service_check_result_t *out)
{
    sc_init();
    SC_LOCK();
    bool ok = sc_get_locked(index, current_token, out);
    SC_UNLOCK();
    return ok;
}

void service_check_poll(void) {sc_init(); sc_run();}

typedef struct {uint8_t enabled, notify, reserved[2]; uint32_t interval_s;} sc_watch_blob_t;

void service_check_init(void)
{
    sc_init();
    nvs_handle_t nvs;
    sc_watch_blob_t blob;
    size_t size = sizeof blob;
    bool loaded = false;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        /* Missing or invalid means OFF, never an inferred interval. */
        loaded = nvs_get_blob(nvs, "svc_watch", &blob, &size) == ESP_OK && size == sizeof blob
            && blob.enabled <= 1 && blob.notify <= 1 && !blob.reserved[0] && !blob.reserved[1];
        nvs_close(nvs);
    }
    service_watch_config_t stored = {.enabled = blob.enabled, .notify = blob.notify, .interval_s = blob.interval_s};
    if (!loaded || !sc_watch_valid(&stored)) return;
    SC_LOCK();
    sc_watch = stored;
    sc_watch_next = sc_now_ms() + (uint64_t)stored.interval_s * 1000u;
    SC_UNLOCK();
    if (stored.enabled) (void)sc_start_worker();
}

void service_watch_get(service_watch_config_t *out)
{
    sc_init();
    SC_LOCK();
    *out = sc_watch;
    SC_UNLOCK();
}

esp_err_t service_watch_set(const service_watch_config_t *config)
{
    sc_init();
    if (!sc_watch_valid(config)) return ESP_ERR_INVALID_ARG;
    if (config->enabled && sc_start_worker() != ESP_OK) return ESP_ERR_NO_MEM;
    service_watch_config_t stored = *config;
    sc_watch_blob_t blob = {.enabled = stored.enabled, .notify = stored.notify, .interval_s = stored.interval_s};
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "svc_watch", &blob, sizeof blob);
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err != ESP_OK) return err;   /* RAM keeps the previous watch */
    SC_LOCK();
    sc_watch = stored;
    sc_watch_next = sc_now_ms() + (uint64_t)stored.interval_s * 1000u;
    if (!stored.enabled) {memset(sc_watch_fails, 0, sizeof sc_watch_fails); memset(sc_watch_alerted, 0, sizeof sc_watch_alerted);}
    SC_UNLOCK();
    return ESP_OK;
}

static void sc_notify(int index, bool recovered)
{
    tailnet_forward_rule_t rule;
    char message[160];
    bool named = sc_rule(index, &rule) && rule.name[0];
    snprintf(message, sizeof message, recovered
             ? "Service watch: rule %d%s%.31s%s answers again (TCP handshake from this gateway)."
             : "Service watch: rule %d%s%.31s%s gave no TCP answer twice in a row. This is not proof the peer is offline.",
             index + 1, named ? " (" : "", named ? rule.name : "", named ? ")" : "");
    (void)ntfy_integration_queue_event(message);
    mqtt_integration_publish_now();
}

static uint64_t sc_now_ms(void) {return (uint64_t)esp_timer_get_time() / 1000;}
static bool sc_rule(int index, tailnet_forward_rule_t *rule) {return tailnet_forward_get(index, rule, NULL);}
static bool sc_admit(void) {return homelab_ops_admit();}
static esp_err_t sc_start_worker(void) {return homelab_ops_start_optional_worker();}

static void sc_path(const tailnet_forward_rule_t *rule, sc_path_t *out)
{
    microlink_t *ml = tailscale_get_microlink();
    out->connected = tailscale_is_connected() && ml;
    ml_policy_status_t policy;
    ml_policy_get_status(&policy);
    out->authority = policy.authority_ready;
    if (!out->connected) return;
    struct in_addr literal;
    out->resolved_ip = inet_pton(AF_INET, rule->destination, &literal) == 1
        ? ntohl(literal.s_addr) : microlink_resolve(ml, rule->destination);
}

static int sc_connect(uint32_t ip_hbo, uint16_t port, uint32_t timeout_ms)
{
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) return -1;
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {close(fd); return -1;}
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(port), .sin_addr = {.s_addr = htonl(ip_hbo)}};
    int result = connect(fd, (struct sockaddr *)&a, sizeof a);
    if (result < 0 && errno != EINPROGRESS) {close(fd); return 0;}
    fd_set writable;
    FD_ZERO(&writable);
    FD_SET(fd, &writable);
    struct timeval timeout = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    int ready = result == 0 ? 1 : select(fd + 1, NULL, &writable, NULL, &timeout), error = 0;
    socklen_t size = sizeof error;
    bool ok = ready > 0 && getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0 && !error;
    close(fd);
    return ready < 0 ? -1 : ok ? 1 : 0;
}
