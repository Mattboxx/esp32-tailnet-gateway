# Persistent development instructions

## Mandate and reading order

Develop **ESP32 Tailnet Gateway — Mattboxx Edition** (formerly ESP32 Homelab Gateway) incrementally, not merely
its documentation. The user-approved full mandate is preserved without feature
removal in [docs/MASTER-DEVELOPMENT-PROMPT.md](docs/MASTER-DEVELOPMENT-PROMPT.md).
Read this file, [GOALS.md](GOALS.md), the full master mandate, then:

1. `docs/NEXT-STEPS-FOR-AGENT.md` — exact next actionable checkpoint.
2. `docs/FEATURE-IMPLEMENTATION-MATRIX.md` — implementation versus validation.
3. `docs/VALIDATION-STATUS.md` and `docs/ARCHITECTURE-DECISIONS.md`.
4. Relevant source and tests; never infer implementation from a README alone.

Higher-priority instructions and the user's latest explicit constraints prevail.
The mandate authorizes ordinary local implementation, tests, documentation,
necessary scoped refactoring, local branches and local commits. It is not
authorization for external writes or production network changes.

## Permissions and safety boundaries

- **No push, physical flash/OTA install, release/tag publication, destructive
  external operation or remote repository URL change without explicit user
  authorization.** Do not reuse old flashing permission for a newer candidate.
- Do not change live Tailnet policies, credentials, device settings or network
  exposure just to run a test without appropriate explicit authority.
- Keep public stable artifacts intact. Never relabel an old image as a new one.
- Preserve pre-existing dirty files, untracked work and private build outputs.
  Inspect root and nested Git status before editing. No destructive reset,
  checkout, cleanup, history rewrite or broad filesystem removal.
- Never commit real credentials, NVS backups, private map/log/packet captures,
  device identifiers or environment-specific secrets. Use synthetic examples.
- Do not weaken authentication, encryption, certificate verification or test
  expectations to obtain a passing result. No mandatory telemetry/log uploads.
- Preserve licenses, copyright, upstream links and original attribution. Tailscale,
  WireGuard, DERP and MicroLink are not Mattboxx inventions.

## Autonomous execution and checkpoints

Select the first incomplete **available** task by P0→P1→P2→P3 and dependency
order in `docs/DEVELOPMENT-ROADMAP.md`; do not repeatedly ask what to do next.
Use targeted analysis, implement multiple related capabilities, integrate,
perform essential checks and continue. A hardware/credentials/authorization blocker is scoped to that test:
prepare its procedure and continue independent offline work. Never manufacture
a hardware result or mark the whole roadmap done because one increment is done.

At each meaningful checkpoint update the matrix, validation status, decisions
when applicable and exact next steps. Record source version, executed commands,
results, unresolved regressions and missing tests. End-of-session handoff must
be sufficient to resume without redesign. Reports to the owner are concise
Italian; firmware UI, new code/comments and maintained project docs use English.
The original Italian mandate is an intentional verbatim archival exception.

Never delete an approved requirement. Retain a blocked/deferred item with its
technical reason and nearest feasible alternative. Superseded planning docs
must point to the authoritative roadmap; older rejection/defer decisions do not
override the newer master mandate (notably timed rules, export and Ethernet).

## Architecture and resource constraints

Six areas: Connectivity Core; Network Gateway; Recovery & Device Management;
Monitoring & Diagnostics; Automation & Integrations; Configuration & Management.
These are ownership boundaries, not a requirement for a heavyweight rewrite.
Keep routing/control and essential administration independent of optional
MQTT/ntfy/HA/SNMP failures and server availability. Independence still requires
power, uplink/router/Internet and the applicable VPN infrastructure.

- Preserve all functioning Mattboxx features, Tailscale/Headscale compatibility,
  direct/DERP, routing/NAT/firewall, AP gateway and separate AP-side forwarding,
  LAN→Tailnet, WoL, MQTT/HA, ntfy, SNMP, 4via6, exit-node modes, Web/API, persistent
  settings and user-controlled OTA. Document demonstrated incompatibilities.
- Risky new behavior starts OFF; unavailable modules report unavailable. Do not
  equate peer visibility, installed mapping, sent WoL or control connection with
  service authorization, verified reachability, power-on or working data plane.
- Authentication to administer the ESP is separate from network authorization.
  Source CIDR filtering is not authenticated client identity.
- Authorize original packets before NAT/4via6. Treat PacketFilter/PacketFilters,
  source/key ownership, revocation and return state explicitly. Do not claim
  official-client policy parity without sufficient real evidence.
- Bound parser sizes, state, queues, retries, timeouts, sockets, polling and job
  concurrency. Measure thresholds; label unmeasured budgets as estimates.
  Do not block the TCPIP core on integration jobs or lifecycle locks.
- Do not silently widen unsupported policies or discard security-relevant
  configuration. Invalid authority must fail closed. Distinguish a transient
  transport loss from malformed/revoked policy and test the availability tradeoff.
- Keep NVS schema/app identity `esp32_tsr`/updater identity stable. Validate and
  persist before publishing RAM state. Test migration and rollback honestly.
- Do not claim Ethernet from netif counters, or signing/Secure Boot/encrypted
  flash/NVS/out-of-band recovery unless actually implemented and qualified.

## Source, build and tests

The actual dependency is `external/microlink`, not the latest remote branch.
Inspect its HEAD, dirty files, configured sources and effective SDK flags.
Dependency fixes need a reviewed nested commit and parent gitlink before a
future release; a clean old submodule SHA does not include uncommitted fixes.

Current supported build: ESP32-S3 N16R8, ESP-IDF 5.5.3, PlatformIO environment
`esp32-s3`. Build outside protected Documents when necessary, without changing
host security settings:

```powershell
$env:PLATFORMIO_BUILD_DIR=Join-Path $env:TEMP 'mattboxx-esp32-build-0114'
& "$env:USERPROFILE/.platformio/penv/Scripts/platformio.exe" run -e esp32-s3
```

Do not copy a stale `.pio/build` image when this override is active. Keep exact
candidate binary/ELF hashes in ignored `build/development-<version>/` records.
The user's token-efficient mode supersedes per-function test/build cadence.
Implement meaningful actual-code behavior tests alongside blocks, but defer
their full execution to consolidated validation. Prefer integration builds at
the end of the security block and after overall integration; the user's latest
clarification permits additional quick builds to prevent important accumulated
errors. Only fast indispensable critical checks during development;
no repeated full suites, browser/sanitizer/soak runs or physical-device use.
Save command logs locally and print only compact outcomes/relevant failures.
Read operating files once per session, then only relevant changed sections.
Use at most ten lines for block updates; do not stop after a module or ask for
the next approved roadmap item. Leave unexecuted tests explicitly pending.

Coverage must include:
positive/negative cases, limits, malformed data, OOM, timeout, initial/disabled
states, configuration/reconnect/reboot/persistence interactions as applicable.
String/file-presence guards alone are not behavior tests. Preserve broader
suites/browser coverage for final consolidated validation. The physical stable
ESP is reserved for final authorized hardware qualification with a verified
backup and concrete recovery path. Earlier flash authority is not reusable.

Consolidated offline entry point: `python tools/validate_all.py --build --browser`;
Linux sanitizers: `python tools/validate_all.py --sanitizers --browser` with the
pinned SDK/cJSON dependencies. `--only <driver,...>` is a targeted rerun, never
the full campaign. Complete logs and scope-aware JSON summaries stay under
ignored `build/validation-*`. Do not run any `*_device.py` merely by globbing
all Python test files; those can mutate the physical stable board.

Primary current authorization driver: `tools/test_tailnet_authorization.py`.
`CJSON_SOURCE` selects the pinned SDK's `components/json/cJSON/cJSON.c` on
Windows; Linux can use `libcjson-dev`. `LWIP_SOURCE` selects the pinned SDK lwIP
tree for `tools/test_tailnet_sdk.py`. Host sanitizers and mock crypto/interfaces
must be identified as such. Two independent real clients/direct+DERP/physical
NVS/OTA/heap/socket/stack/soak results remain separate acceptance gates.

Before sharing a source checkpoint, run credential/history scans and review
diffs in both worktrees. Successful scans/builds do not prove security or
hardware compatibility. Keep detailed validation internal; future user-facing
release notes describe actual behavior, not fabricated qualification.
