/* On-demand LAN -> Tailnet destination check; see service_check.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "service_check.h"
#include "service_lease.h"
#include "homelab_ops.h"
#include "tailscale_config.h"
#include "microlink.h"
#include "ml_policy.h"
#include "esp_timer.h"
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
#define SC_LOCK() xSemaphoreTake(sc_lock, portMAX_DELAY)
#define SC_UNLOCK() xSemaphoreGive(sc_lock)
static SemaphoreHandle_t sc_lock;

/* --- service check core (begin) --- */
static service_check_result_t sc_results[TAILNET_FORWARD_MAX];
static struct {bool active; int index; uint32_t token;} sc_pending;

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
    SC_LOCK();
    if (sc_pending.active && sc_pending.index == index && sc_pending.token == token) {
        sc_results[index] = r;
        sc_pending.active = false;
    }
    SC_UNLOCK();
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
