/* On-demand destination check for one LAN -> Tailnet service rule.
 * The ESP itself opens one bounded TCP connection to the rule's Tailnet
 * destination, which is the same remote leg forwarded LAN clients use (they
 * are source-translated to this node). It works for disabled rules, so a
 * service can be verified before any LAN exposure is enabled. It proves a TCP
 * handshake only: not application health, not the local source filter and not
 * the LAN client's own path to this device. UDP has no handshake and is
 * reported as unverifiable instead of guessed. Original implementation,
 * Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "tailnet_forward.h"

typedef enum {
    SC_NONE, SC_PENDING, SC_REACHABLE, SC_NO_ANSWER, SC_UDP_UNVERIFIABLE,
    SC_NO_CONTROL, SC_NO_AUTHORITY, SC_UNRESOLVED, SC_RESOURCE, SC_LOCAL_ERROR,
    SC_CHANGED, SC_STATE_COUNT
} service_check_state_t;

typedef struct {
    uint8_t state;
    uint32_t token;        /* service_lease_token() of the checked rule */
    uint32_t latency_ms;
    uint32_t resolved_ip;  /* host order; 0 when not resolved */
    uint64_t observed_ms;  /* uptime; 0 while pending */
} service_check_result_t;

#define SERVICE_CHECK_COOLDOWN_MS 5000u
#define SERVICE_CHECK_TIMEOUT_MS 2000u

/* ESP_ERR_INVALID_ARG bad index; ESP_ERR_INVALID_STATE rule changed;
 * ESP_ERR_NOT_FINISHED another check pending; ESP_ERR_TIMEOUT cooldown;
 * ESP_ERR_NO_MEM optional worker unavailable. */
esp_err_t service_check_request(int index, uint32_t expected_token);
/* False when there is no result for the rule's current identity. */
bool service_check_get(int index, uint32_t current_token, service_check_result_t *out);
/* Optional operations worker only: at most one socket, bounded timeout. */
void service_check_poll(void);
const char *service_check_state_name(unsigned state);
const char *service_check_summary(unsigned state);
const char *service_check_next_step(unsigned state);
