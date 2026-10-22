/* Passive, evidence-limited diagnostics. No I/O, allocation or hidden probes. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    const char *code;
    const char *summary;
    const char *next_step;
} service_diagnostic_t;

static inline service_diagnostic_t service_diagnose(bool enabled, bool uplink_ipv4,
                                                    bool control_connected, bool resolved,
                                                    bool installed, bool runtime_error)
{
    if (!enabled) return (service_diagnostic_t){
        "disabled", "Rule disabled", "Enable and save this rule only if its LAN exposure is intended."};
    if (!uplink_ipv4) return (service_diagnostic_t){
        "uplink_no_ipv4", "Uplink has no IPv4 address",
        "Check the local WiFi connection and DHCP/static settings. This does not identify a router or Internet failure."};
    if (!control_connected) return (service_diagnostic_t){
        "control_not_ready", "Tailscale control session is not ready",
        "Check the Tailscale page for authentication/startup details. Existing data sessions may still work; this is not a data-plane test."};
    if (!resolved) return (service_diagnostic_t){
        "destination_unresolved", "No Tailnet IPv4 destination is available",
        "Check the saved 100.64.0.0/10 address or MagicDNS peer name and the reported runtime error. The peer is not proven offline."};
    if (!installed) return (service_diagnostic_t){
        "mapping_not_installed", "Forwarding mapping is not installed",
        "Check the runtime error and listener conflicts, then reload after the manager refreshes. No service test has run."};
    if (runtime_error) return (service_diagnostic_t){
        "runtime_error", "Mapping installed with a runtime warning",
        "Review the reported runtime error before using this rule. Remote service reachability is not verified."};
    return (service_diagnostic_t){
        "mapping_installed", "Mapping installed; service not tested",
        "Connect from an allowed LAN client using the ESP uplink IP and listen port. If it fails, check destination service authentication, listener/firewall and tailnet policy."};
}

/* Evidence from an on-request destination test and the policy gate's admitted
 * replies refines the passive state. Still evidence, never a grant: a reply
 * is per destination tuple, not per LAN client. */
enum {SERVICE_EVIDENCE_NONE, SERVICE_EVIDENCE_REACHABLE, SERVICE_EVIDENCE_NO_ANSWER};
static inline service_diagnostic_t service_diagnose_evidence(service_diagnostic_t base, int check,
                                                             bool replied, bool accepted_seen,
                                                             bool rejected_seen)
{
    if (!strcmp(base.code, "disabled") && check == SERVICE_EVIDENCE_REACHABLE) return (service_diagnostic_t){
        "ready_to_enable", "Rule disabled; destination test reachable",
        "Enable the rule when this LAN exposure is intended; prefer an expiry for temporary access."};
    if (strcmp(base.code, "mapping_installed")) return base;
    /* The remote tuple is shared by destination tests and other rules. Its
     * reply evidence cannot override rejected-only ingress for THIS binding. */
    if (rejected_seen && !accepted_seen) return (service_diagnostic_t){
        "source_rejected", "Mapping installed; only rejected LAN packets seen",
        "LAN packets reached the listener but did not match the allowed source or an active expiry. Compare the client address with the source CIDR."};
    if (replied) return (service_diagnostic_t){
        "service_replied", "Mapping installed; the Tailnet service replied recently",
        "A reply was admitted for this remote service tuple, possibly from a destination test or another rule. Delivery through this rule to a LAN client and application correctness are not verified."};
    if (check == SERVICE_EVIDENCE_NO_ANSWER) return (service_diagnostic_t){
        "destination_no_answer", "Mapping installed; destination test got no TCP answer",
        "Check that the peer is online, the service listens on that port and the Tailnet ACL allows this gateway."};
    if (check == SERVICE_EVIDENCE_REACHABLE) return (service_diagnostic_t){
        "destination_reachable", "Mapping installed; destination test reachable",
        "Connect from the allowed LAN client using the ESP uplink IP and listen port."};
    return base;
}
