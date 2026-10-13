# ESP32 Tailscale Gateway 0.1.31-Mattboxx-1.10-dev.18

Beta hotfix, October 13, 2026. Supersedes dev.11; stable 1.8 remains unchanged.
Enable beta updates to discover this compatible newer custom build.

## Original credits

Based on [Csontikka's router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
through v0.1.31 and [microlink](https://github.com/Csontikka/microlink).
Original authors' credits, contributors and component licenses remain intact.

## What was wrong and what changed

**Startup stuck on Registering:** the supplied/live logs showed a failed WG
task allocation. Free RAM alone did not guarantee a large contiguous stack.
Create worker stacks in decreasing size order (12KB, 10KB, 10KB, 8KB, 6KB),
without shrinking them. TLS coordination and cache loading wait until every
worker exists. Partial startup is rolled back before bounded 2/4/8/16-second
memory retries; incomplete cleanup is not retried. Startup failure/retry is
shown explicitly in both dashboard views.

**AP recovery could fail after long uptime:** replace per-request dynamic 8KB
workers with one statically reserved worker. Requests coalesce, grace periods
remain, and a failed mode change is retried without allocating another stack.
Ignore WiFi recovery requests during intentional shutdown/restart. Preserve
the user's enabled/auto-off AP policy; do not force AP ON.

**Control ping worked but real tunnel requests timed out:** live interface
counters showed requests entering and replies leaving the tunnel, while the
host received no reply bytes. Relay traffic incorrectly kept a saved direct
endpoint alive. Track authenticated direct activity separately: nonempty
relay-delivered packets select relay replies immediately, including asymmetric
paths. Empty relay keepalives alone retain direct paths active within the last
30 seconds. Preserve existing sessions and continue direct discovery/upgrades.

**Memory and diagnostics:** allocate the 4KB previous-boot log in PSRAM when
available, prefer PSRAM for ordinary allocations above 1KB and initialize JSON
allocation hooks once before application workers. DMA and task stacks remain
internal, with their existing sizes and internal reserve. Treat a zero STUN
baseline port as unknown. Numeric WiFi disconnect reasons include shutdown
state and memory budgets. The UI says Previous-boot log because a retained
log from an ordinary software restart is not proof of a crash.

**Concurrent logins with the timer OFF:** all session expiries were identical,
so a full table repeatedly replaced slot zero, including a just-used session.
Concurrent clients could kick each other out even immediately after renewal.
Track activity independently of expiry; prefer empty/expired slots, then evict
the truly least recently used session. Keep the four-session limit, cookie
validation, optional idle timeout and password policy unchanged.

The dev.11 input-recursion correction remains. No feature or stored setting
is removed: independent AP and LAN-to-Tailnet forwarding, MQTT/Home Assistant,
ntfy commands and notifications, named WOL targets, configurable Web UI
port/password/session, route and exit controls, Ethernet, diagnostics, SNMP
and opt-in GitHub stable/beta/manual/automatic updates are preserved.
No external log upload is added. Dev.12–17 were local test candidates whose
remaining problems were caught before release; they were not published.

## Verification

- Actual-C regressions exercise one reserved AP stack, 1,000 coalesced requests,
  grace/retry timing, competing generations and shutdown suppression.
- Inject failure at all five startup allocation points; check cleanup,
  ready-barrier ordering and bounded retries. Test relay recovery, healthy
  direct retention, direct upgrades and 32-bit clock wrap with the actual
  endpoint-selection function.
- Feature-preservation and 21 actual-SPA browser scenarios pass. The exact
  linked IPv4 callers retain forwarding policy and their existing stack budgets.
- An actual-C session regression detects the dev.17 no-timeout eviction bug
  and passes after the fix: 10,000 creations, active-session retention,
  expired/cleared slots, invalid-token rejection and timeout-window changes.
- The exact ESP32-S3 OTA image booted in 36 seconds. Eight saved-setting groups
  were unchanged, compared only in memory; no private snapshot was saved.
- Two software restarts completed WiFi/Tailscale/MQTT startup and real
  authenticated Tailnet HTTP in 47 seconds each. Identity/configuration
  stayed unchanged; both resets were SW, not PANIC. Eight repeated unchanged
  AP-policy saves coalesced correctly and the AP stayed OFF.
- Eight additional authenticated logins preserved two active sessions with
  the timeout OFF. Saved settings were unchanged and test sessions were logged
  out afterward. The four-session limit is unchanged.
- Registration is not the same as peer-session readiness. The regression also
  checks real HTTP with bounded read-only retries, rejecting further resets
  or an unavailable data path rather than accepting a control ping alone.
- An overnight spot-check of preceding candidate dev.17 observed 58,066 seconds
  of uptime, a SW last reset,
  WiFi/Tailscale/MQTT available, no startup error and AP OFF. This is a snapshot,
  not a continuous 16-hour network-availability measurement.
- A 302-second ntfy HTTPS test on the exact dev.18 image completed three `info`
  commands and verified
  replies at the configured broker, with MQTT connected and no reboot.
  Minimum sampled remaining ntfy stack: 4,412 B; internal heap: 12,515 B.
  These samples do not measure all transient peaks. The command-availability
  policy was restored; private notification bodies were not printed or saved.
- Thirty actual authenticated Tailnet HTTP samples completed in 121 seconds
  while SNMP was enabled, without an observed reboot. Fifteen protected GET
  endpoints rejected anonymous requests.
- SNMP v1/v2c returned twelve real Tailnet replies across repeated installer
  ticks. Both full 82-object LAN walks, read-only/invalid-message checks and
  three live disable/enable cycles passed. A 301-second enabled soak completed
  51 queries without observed WiFi/Tailscale loss or restart, with zero LAN UDP
  retransmissions. The agent was restored OFF with community/name/contact/
  location unchanged. Earlier diagnostic retries exposed test-session and
  stale-reply handling defects; neither is counted as a successful soak.
- GitHub's regression/credential-history workflow and C/C++/Python CodeQL
  passed on the firmware-source commit. Source/history, dependency contents
  and packaged-image pattern checks reported no findings; this is not an
  exhaustive guarantee that no sensitive data could exist.

## Assets and updating

Use `firmware.bin` for **System → Firmware update**, or **Install latest update**
with the beta channel enabled. The Windows ZIP includes esptool, its license,
hashes and `UPDATE_KEEP_SETTINGS.bat`. These update paths preserve settings.
`firmware-factory.bin` / `CLEAN_INSTALL_ERASE_ALL.bat` are for a fresh install
and erase saved settings only after explicit confirmation.

OTA SHA-256:

`f43cfa707b47af74a01fb62ef66bf4936af677ed67b6e3b6cce66dda9f009e86`

Targets ESP32-S3 N16R8 with 8MB octal PSRAM and the existing 4MB partition layout.
Application use: 1,698,272 / 1,966,080 B; static RAM: 85,548 B.
Factory assets contain blank NVS, not a backup of the reference board.

## Limits

This is a tested beta hotfix, not a claim of universal or long-duration
stability. Bounded WiFi-board tests cannot establish reliability on every
network. Physical Ethernet hardware, arbitrary remote forwarding services,
full exit-node Internet throughput and the Home Assistant frontend were not
revalidated by these checks. Pattern scanning and CodeQL do not guarantee that
every possible bug or sensitive value has been found. Previous reset history
is retained; old entries do not mean that the new image has just crashed.
