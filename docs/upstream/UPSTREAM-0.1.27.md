# Upstream v0.1.27 integration — Mattboxx 1.6 development

Target: `0.1.27-Mattboxx-1.6-dev`. Integration date: 2026-09-28.
Previous stable release: `v0.1.19-Mattboxx-1.5`, unchanged.

Router comparison: upstream v0.1.19 through v0.1.27 (`331b9dc`). The single
later main-branch commit is outside this version-pinned alignment.
Microlink target: `7de6a93684a34991fdfa1eeb9281e08523646ef7`, exactly the
dependency used by upstream router v0.1.27, merged into the Mattboxx fork.
Credit belongs to Csontikka/microlink and the upstream contributors, including
the timmills and gszigethy changes credited in the upstream release notes.

## Coverage by upstream release

| Release | Integrated improvements |
| --- | --- |
| 0.1.20 | Bounded discovery/WireGuard work per loop; allocation diagnostics; current capability version in `/key`; registration failure handling; NodeID-based removed-peer handling; optional IPNVersion setting; persist-only exit-node selection; one-boot crash signatures for local diagnostics. |
| 0.1.21 | Cached per-peer discovery shared secret, offline-peer backoff, no CallMeMaybe echo storm, stable trusted endpoints and no unnecessary handshake on endpoint changes. |
| 0.1.22 | Endpoint updates only when needed, one discovery PONG per PING, automatic MTU 1280 on direct and relayed paths. |
| 0.1.23 | Reported client version retained in every Hostinfo message. |
| 0.1.24 | Automatic AP-subnet advertisement, separate from manual routes; pinned active TCP and out-of-order buffer limits. |
| 0.1.25 | Serialized/coalesced initialization, long-cookie authentication, shared link-state qualifiers; coordinated microlink task shutdown and DERP/control-buffer cleanup. |
| 0.1.26 | WireGuard device and queued-packet cleanup with key-material clearing on teardown. |
| 0.1.27 | No channel-realignment reboot, actual radio-channel reporting and one shared Hostinfo builder. |

## Mattboxx adaptations and preserved behavior

- Existing installations keep their current route-advertisement scope.
  Automatic AP advertisement is opt-in on upgrades, and on by default only
  for fresh installations. No manual `ts_routes` contents are overwritten.
- Route previews use caller-owned buffers. Lines are trimmed and deduplicated,
  overlong input is rejected, and AP/4via6/exit-node routes are composed with
  bounds checks. The running VPN retains immutable boot-lifetime route and
  client-version storage. Saved preview and active state are distinguished.
- Connection initialization is mutex-serialized; redundant SNTP/connect tasks
  are coalesced. A static mutex avoids falling back to unprotected execution
  on allocation failure. The fork's existing **device-restart-based VPN
  reconfiguration remains**: automation/routing consumers retain the published
  handle, so upstream's live destroy/recreate policy is not blindly imported.
  Microlink's own shutdown fixes are present, but full live application-level
  reconnect is not newly promised by this release.
- Cookies are read in full up to a 4096-byte bound. Exact cookie-name matching
  and constant-time token comparison avoid both substring matches and the
  earlier small-header logout. Authentication/session-timeout options remain.
- The automatic AP-advertisement switch is exposed in Home Assistant/MQTT;
  ntfy info reports its configured state. Active routes include 4via6 and
  exit-node routes while preserving the private-detail gate in ntfy.
- WOL and its saved device names, MQTT/HA controls, ntfy commands, configurable
  web port, LAN-to-Tailnet forwarding, separate AP-side forwarding, AP policy,
  CPU/per-core monitoring and DHCP input hardening are preserved.
- No telemetry sender, external log/crash upload, automatic GitHub downloader,
  public speed test or hard-coded public DNS fallback is restored. Upstream's
  telemetry-specific hunk is omitted. Microlink warning-level peer-identity
  redactions and application 4via6 hooks remain, including merge conflicts.
- Bench-only forced-roam and reconnect-burst HTTP endpoints are not exposed in
  the general firmware. WiFi scan results include BSSID diagnostics, and the
  dashboard reports the radio channel separately from the configured channel.
- Ethernet remains outside this release, as it also remains outside upstream
  v0.1.27. No new GPIO assumptions or hardware requirements are introduced.

## Validation

Host C regression tests cover route composition/deduplication/capacity, long
cookies/exact token matching, client-version input, DHCP request bounds, MQTT
values/indexes and CPU arithmetic. Python guards check retained custom source
components, privacy exclusions, deferred exit selection, channel-roam behavior,
network defaults and non-mutating route composition. These are host/static
tests, not proof of runtime behavior on the board.

The SPA is syntax-checked and its element IDs checked for duplicates. The
ESP32-S3 build succeeds with 71,512 bytes of RAM data/BSS (21.8%) and
1,613,083 bytes in the application partition (82.0%); the generated firmware
image is 1,613,456 bytes. The final checks include two C regression binaries,
five Python integration guards, HTML/JavaScript validation, duplicate-ID
validation, a full tracked/history/artifact credential-pattern scan of the
parent repository, and a tracked-content scan of the microlink submodule.

Still required on hardware: boot/OTA, repeated WiFi roaming, direct and DERP
traffic, exit-node bulk downloads, peer removals, AP clients and DHCP, AP route
approval/migration, MQTT/HA, ntfy/WOL and LAN-to-Tailnet TCP/UDP regression.
Upstream's own device measurements are not claimed as tests of this fork.
No board flash, GitHub release promotion or replacement of the 1.5 assets is
part of this source-alignment step.
