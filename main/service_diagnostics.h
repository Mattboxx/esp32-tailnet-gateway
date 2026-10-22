/* Passive, evidence-limited diagnostics. No I/O, allocation or hidden probes. */
#pragma once
#include <stdbool.h>
#include <stddef.h>

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
