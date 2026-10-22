/* Numeric, read-only local metrics. No identifiers/targets/secrets. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
/* OIDs: 1.3.6.1.4.1.99999.2.<metric>.0. 99999 is an unassigned local tree. */
enum {
    SNMP_OPS_AVAILABLE=1, SNMP_OPS_INTERNAL_FREE, SNMP_OPS_INTERNAL_MIN,
    SNMP_OPS_INTERNAL_LARGEST, SNMP_OPS_PSRAM_FREE, SNMP_OPS_PSRAM_MIN,
    SNMP_OPS_PSRAM_LARGEST, SNMP_OPS_SOCKETS_USED, SNMP_OPS_SOCKET_LIMIT,
    SNMP_OPS_WORKER_RUNNING, SNMP_OPS_WORKER_STACK_RAW, SNMP_OPS_AUTHORITY_READY,
    SNMP_OPS_POLICY_PEERS, SNMP_OPS_RETURN_FLOWS, SNMP_OPS_FORWARD_ENABLED,
    SNMP_OPS_FORWARD_INSTALLED, SNMP_OPS_FORWARD_ACCEPTED, SNMP_OPS_FORWARD_BLOCKED,
    SNMP_OPS_MQTT_CONNECTED, SNMP_OPS_CONTROL_CONNECTED, SNMP_OPS_RESET_REASON,
    SNMP_OPS_FORWARD_REACHABLE, /* rules whose current destination test was reachable */
    SNMP_OPS_FORWARD_REPLIED,   /* rules with an admitted reply from their service */
    /* Health checks: 0 disabled 1 not configured 2 unverified 3 ok 4 degraded
     * 5 down 6 unknown 7 resource-deferred 8 stale */
    SNMP_OPS_HEALTH_GATEWAY, SNMP_OPS_HEALTH_DNS, SNMP_OPS_HEALTH_INTERNET, SNMP_OPS_HEALTH_TAILNET,
    SNMP_OPS_LIMIT
};
typedef struct {uint32_t value[SNMP_OPS_LIMIT];} snmp_operational_metrics_t;
/* Agent task only; bounded, allocation-free, no network or configuration writes.
 * The provider is called on demand at most once/second, never from a timer. */
typedef void (*snmp_operational_provider_t)(snmp_operational_metrics_t *out);
void snmp_agent_set_operational_provider(snmp_operational_provider_t provider);
