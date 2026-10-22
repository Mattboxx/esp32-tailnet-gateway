# NVS keys added in the 1.14 development line

All keys live in the existing `tsr` namespace; the app/NVS/updater identity is
unchanged. Each record is validated before use (magic/version/checksum or
range checks) and an invalid record means the feature is **off**, never a
guessed configuration. Stable 1.13 does not read any of these keys.

| Key | Owner | Contents | Invalid/missing means |
|---|---|---|---|
| `ops_registry` | homelab_ops.c | registry profiles per WoL device, operations settings | defaults, monitoring off |
| `ops_health` | health_monitor.c | Health Monitor targets/cadence | Health Monitor off |
| `tn_leases` | service_lease.c | temporary-access ledger (bindings, expiry, tombstones) | timed rules closed, not opened |
| `cfg_profile` | config_profiles.c | active profile and one rollback record | no profile, no rollback |
| `eth_cfg` | eth_uplink.c | Ethernet pins/IP/preference | Ethernet off |
| `svc_watch` | service_check.c | Service watch enable/notify/interval | watch off |
| `ntfy_sysev` | ntfy_integration.c | system-events switch (separate so the ntfy v1 record keeps its flag mask) | events off |

## Downgrade to stable 1.13: read this first

Stable 1.13 ignores the new keys, so the settings above simply stop applying.
The one with a security consequence is **temporary service access**: 1.13 has
no lease engine, so a LAN → Tailnet rule that is enabled with an expiry in the
development line becomes a **permanent** enabled rule under 1.13. Before a
downgrade, disable or delete temporary rules (or export them, then review after
the downgrade). Upgrading again restores the ledger; tombstoned bindings stay
closed.

Physical NVS power-loss during these writes is not qualified; logical
validate-then-commit behavior is covered by host tests.
