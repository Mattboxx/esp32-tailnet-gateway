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
| `cell_cfg` | cell_uplink.c | cellular modem pins, APN, PIN, mode (3.0) | cellular off |
| `txn_undo` | nvs_params.c | undo journal of a multi-key settings save in progress (previous value or absence of each key, CRC-32); dropped when the save is kept, applied and dropped on failure or at the next boot after a power loss; a damaged journal is discarded without being applied (after 3.0.1) | absent |
| `hist_cfg` | history.c, nvs_flags.c | event history, trends, settings copy before updates as one byte (bits 0–2, bit 7 marks the record; after 3.0.1) | all off; damaged = all off |
| `hist_ev`, `hist_mx`, `hist_snap` | history.c | 3.0.0/3.0.1 per-switch keys: read only while `hist_cfg` is absent, written after it for a rollback | each off |
| `tsn_cfg` | tailnet_names.c, nvs_flags.c | tailnet names and LAN listener as one byte (after 3.0.1) | off |
| `tsn_en`, `tsn_lan` | tailnet_names.c | 3.0.0/3.0.1 per-switch keys: read only while `tsn_cfg` is absent, written after it for a rollback | off |
| `notify_cfg` | notify_channels.c | Telegram and email settings, write-only secrets (3.0) | both off |
| `ntf_mlv` | notify_channels.c | 3.0.1 email event choice; after 3.0.1 written only for a rollback, the `notify_cfg` record decides (choice kept in its former padding bytes, same size/version) | 3.0.1 record: shared choice |
| `ddns_cfg` | ddns.c | dynamic DNS provider, name, zone, write-only token/URL (3.0.1) | off |
| `tz` | first_boot.c, web_ui.c | POSIX time zone, set by the setup from the browser (3.0.1) or in System | UTC |

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
