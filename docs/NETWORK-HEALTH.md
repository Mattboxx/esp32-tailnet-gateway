# Network and Tailnet health — experimental dev.5

Configure optional checks in **Devices & Recovery → Layered connectivity checks**.
All active checks default OFF, all targets blank/ports zero. Enabling without
targets makes no network request. No mandatory cloud service, public ping,
log upload, power action or automatic ESP reboot is introduced.

| Evidence | What it means | What it does not prove |
|---|---|---|
| WiFi associated | SDK reports an associated station | DHCP, Internet or tunnel health |
| Uplink address available | STA netif is up with an IPv4 address | Router/Internet reachable |
| Control connected | Existing control connection state | Current port grant or data-plane success |
| Policy authority ready | Local authority snapshot ready, not suspended | Permission for every peer/service |
| Gateway TCP | Connection to an operator-selected port on the current uplink gateway | A closed port does not mean the router failed |
| DNS lookup | SDK returned IPv4 for an operator-selected name | Answer can be cached; lookup failure is inconclusive, not Internet down |
| Internet target TCP | Connection to one configured non-local IPv4/port | Whole Internet, TLS identity, or application readiness |
| Tailnet service TCP | Connection to one CGNAT IPv4/cached peer hostname and port | Every peer, route approval, application health, direct versus DERP path |

One check is scheduled per configured 30–3600-second interval. Up to four roles
are visited round-robin. Unconfigured roles are skipped; failures back off up to
16 times that interval. Failure threshold 1–5 avoids declaring a single failed
TCP connection definitively down. No socket is retained between probes. The
existing optional resource guard can defer work. A TCP wait is at most one second;
SDK DNS resolution has its own finite retries and may delay a manual recovery
request queued while it runs. Recovery jobs take priority between health checks.

State is explicit: disabled, not-configured, not-verified, operational, degraded,
down, inconclusive, resource-deferred or stale. Per-check uptime, failures,
reason and next step are shown. Unknown control/policy/cache conditions do not
become a claim that a remote peer is offline or an ACL denied its port. Global
data-plane verification and route approval remain not-verified/unknown.

Settings persist in independent checksummed/versioned `ops_health`, not the WoL
or registry record layout. HTTP is authenticated using the same administration
write-origin rules. A stale failed UI refresh cannot save a replacement config.
Sanitized exports/MQTT state omit configured IPs, hostnames and device names;
the authenticated detailed API includes targets so an administrator can edit them.
HA exposes four check-state sensors. ntfy `info` includes the check states;
opt-in alerts are best-effort, transition-based and do not retry recovery actions.

Implementation is not qualification: actual state/persistence/sanitized-snapshot
and API host fixtures pass with explicit mock boundaries; browser scenarios are
prepared but not executed. Real DNS, TCP, router/DERP faults, resources and soak
are still required. STA-only interface selection must be extended with the actual
conditional Ethernet/uplink implementation. Full monitoring/integration controls,
route-approval evidence and per-peer direct/DERP diagnosis remain roadmap work.
