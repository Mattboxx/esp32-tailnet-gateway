# Codex continuation — presentation published, dev.9 local (2026-10-23)

## Public presentation, independently completed

Published commit `a85681a9920cffa4d21cf9602a4027c6cce47bb3` on public `Main`
in `Mattboxx/esp32-tailscale-gateway-NAS-recovery`. Isolated clone:
`C:/Users/mattb/.codex/workspaces/tailnet-presentation-20261023`.
No firmware, dependency gitlink, release, tag or repository rename was pushed.
The previous stable release is still `v0.1.38-Mattboxx-1.13`.

Public site: <https://mattboxx.github.io/esp32-tailscale-gateway-NAS-recovery/>.
Manual Pages run `39920577535` succeeded. Sensitive Data Check `39920575842`
and CodeQL `39920575900` succeeded. Repository description, homepage and topics
were updated; the official black/green social preview was uploaded, saved and
verified (`usesCustomOpenGraphImage=true`). Existing branding was reused.

The README and all site pages distinguish the 1.14 preview from actual stable
1.13 downloads. Old repository/base path, real asset names, historical guides
and attribution are preserved. No second site or new repository was created.
Site output: 16 pages + custom 404 + 6 redirects. Local and **public HTTPS**
Playwright sweeps each passed 16 pages at 9 viewports, including search,
navigation, touch targets, overflow and console checks. Public assets,
sitemap/robots and custom 404 were checked. Isolated source/history scan:
313 paths, 16 artifact payloads, 1301 historical blobs, **zero findings**.
Evidence is under the isolated clone's ignored `build/presentation-checks/`.

Keep this presentation commit separate from the local firmware branch. Future
firmware publication must integrate its base-path/availability fixes rather
than overwrite public Main with the older local presentation files. Rename
and stable firmware publication still require the owner's next authorization.

## Firmware continuation

Base root `9b67b5af0ef89a9217ac23275f15a3855e31baad` (`mattboxx`);
MicroLink `fa3153b6892d00d0c9a9c42f11c8f1a89c6ea910`, unchanged and clean.
Owner's untracked `docs/COMMUNITY-POSTS.md` remains untouched.
No active device-test process was found before this work. The board has not
yet been changed in this continuation; last qualified/installed image dev.8
and protected stable ota_1 are documented in DEV8-VALIDATION.

Confirmed code paths in the pinned SDK requested a 6144-byte **internal** MQTT
stack on first runtime enable. The dev.8 largest measured internal block was
3456 bytes: this allocation could not fit, but physical OFF-at-boot activation
was not previously tested. The old GOT_IP handler also attempted an unchecked
4096-byte internal `ts_connect` task allocation, even for an existing instance.

Dev.9 changes, without changing network policy or NVS/partitions:

- MQTT manager and MQTT SDK task use PSRAM stacks, same sizes/priorities.
- Project-local adapter is force-included **only in esp-mqtt**, matching SDK
  task creation with `vTaskDeleteWithCaps`. Core-pinned path included. The
  reviewed SDK source hash is required at configuration; SDK files unchanged.
- Tailscale startup reserves before spawning, coalesces duplicate IP events,
  skips spawning for a published instance, uses a paired PSRAM stack and logs
  allocation failure. Failure releases the reservation for a later request.
  Existing five-attempt startup backoff is unchanged. TCB allocation can still
  fail; there is no assertion that all OOM or reconnect failures are eliminated.
- External task stacks are explicitly enabled in tracked defaults, not just
  an ignored generated sdkconfig. Existing PSRAM XIP remains required.
- `tools/test_task_memory.py` compiles the real pinned SDK startup/teardown
  and project launchers against RTOS/allocator fixtures: failure, retry,
  duplicate requests, both core-selection modes and matching deletion. These
  are host tests, not physical fragmentation or two-client network tests.

## Exact candidate and executed checks

WiFi version `0.1.38-Mattboxx-1.14-dev.9`, built with pinned ESP-IDF 5.5.3.
BIN SHA-256 `649c5a3fc4a90bc5d9424fbc53dfd02a2fd68cf85a3a6f10b055e34926d65eb5`;
ELF SHA-256 `c6fca91dd7508f9b0370f7bc26303ca9b84932b7f1169cd331872c96915bcba7`.
BIN 1,878,832 bytes; app 1,878,420 / 1,966,080; static RAM 91,172 bytes.
Exact snapshots: ignored `build/development-0.1.38-Mattboxx-1.14-dev.9/target/esp32-s3/`.
Build log `build/dev9-integration-build-final.log` (PASS). Earlier intermediate
build is not this artifact. Never take an image from stale `.pio/build`.

Targeted Windows **4/4 PASS**: task_memory, runtime_recovery, service_retry,
coord_recovery (`build/validation-20261023-101103-904175/`). Same four Linux
ASan/UBSan drivers **4/4 PASS** (`build/linux-validation-20261023-101138/`).
Full Windows/browser **64/64 PASS** (`build/validation-20261023-101324-583326/`);
full Linux sanitizer **61/61 PASS** (`build/linux-validation-20261023-101335/`).
Build is separately PASS, not counted in the 64-check Windows run. Later new
MQTT activation harness tests are tracked separately until a consolidated rerun.

The owner explicitly authorized installing **this exact dev.9 WiFi hash** on
the bench ESP, preserving configuration, backups and stable ota_1. Before any
write, reidentify device/layout/process ownership and verify backup/stable-slot
integrity. Normal OTA while ota_0 is running would overwrite stable ota_1:
first boot the verified preserved stable, then guarded OTA only into ota_0.
No authorization to publish dev.9 firmware, rename or issue a release.

## Still open

Physical MQTT enable from OFF after boot, dev.9 stack/heap/socket/continuity
qualification, affected reconnects and version/setting verification. Keep all
remaining dev.8 Quality Gate boundaries, including independent identities and
forced-DERP data, recovery AP, power-loss/rollback and real integrations. W5500
remains compile-only. **NOT READY for a stable release.**
