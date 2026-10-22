/* One definition of a LAN -> Tailnet rule's evidence, shared by the Web API,
 * the sanitized export and MQTT so their diagnoses cannot drift apart.
 * Reads only: no I/O, allocation, probe or lock beyond the callees' own. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "service_check.h"
#include "service_diagnostics.h"
#include "ml_policy.h"

typedef struct {
    service_diagnostic_t diag;
    service_check_result_t check;
    bool checked, replied;
    uint32_t reply_ms;
} service_evidence_t;

/* token is service_lease_token(rule), passed in so callers own that binding. */
static inline void service_evidence_collect(int index, uint32_t token, const tailnet_forward_rule_t *r,
                                            const tailnet_forward_runtime_t *rt, bool uplink,
                                            bool control, service_evidence_t *out)
{
    *out = (service_evidence_t){0};
    out->checked = service_check_get(index, token, &out->check);
    /* Per remote service tuple (shared by rules with the same destination). */
    const uint8_t remote[4] = {(uint8_t)(rt->resolved_ip >> 24), (uint8_t)(rt->resolved_ip >> 16),
                               (uint8_t)(rt->resolved_ip >> 8), (uint8_t)rt->resolved_ip};
    out->replied = rt->resolved_ip && ml_policy_reply_age(r->proto, remote, r->destination_port, &out->reply_ms);
    int check = !out->checked ? SERVICE_EVIDENCE_NONE
        : out->check.state == SC_REACHABLE ? SERVICE_EVIDENCE_REACHABLE
        : out->check.state == SC_NO_ANSWER ? SERVICE_EVIDENCE_NO_ANSWER : SERVICE_EVIDENCE_NONE;
    out->diag = service_diagnose_evidence(
        service_diagnose(r->enabled, uplink, control, rt->resolved_ip != 0, rt->installed, rt->error[0] != 0),
        check, out->replied, rt->last_accepted_s != 0, rt->last_blocked_s != 0);
}
