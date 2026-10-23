# 0.1.38-Mattboxx-1.13-dev.1 — integration candidate

October 20, 2026. All published upstream v0.1.34–v0.1.38 improvements are
merged/adapted on top of the Mattboxx edition. This is a development candidate,
not a replacement of the existing stable release. No external usage reporting,
log/crash uploads, forced update polling or public speed-test service is added.

Original credits: [Csontikka's router](https://github.com/Csontikka/esp32-tailscale-subnet-router),
[microlink](https://github.com/Csontikka/microlink), originally by Cameron Malone,
and the contributors/forks credited upstream. Original notices, licenses and
support links remain. Optional Mattboxx tips do not purchase features or imply
upstream endorsement. [Complete source mapping](../upstream/UPSTREAM-0.1.38.md).

## Included

- Verified DERP relay TLS, WireGuard protocol/key/replay/nonce fixes, strict
  Noise and peer-key decoding, monotonic timestamp persistence.
- Correct, sticky relay measurements and actual-region reporting, silent-peer
  re-handshake and quicker recognition of dead/stalled control sessions.
- v0.1.38's completion-waiting TCPIP lifecycle, not the v0.1.37 teardown race;
  retain custom startup barrier/rollback and restart-based instance lifetime.
- Copy-free WireGuard TX, authenticated profiling and runtime diagnostic
  switching, guarded local recorder snapshots, 32 visible relay measurements.
- Preserve separate AP and LAN-to-Tailnet forwarding, source/MagicDNS controls,
  optional AP policy, named WoL, MQTT/HA, ntfy, routing/exit/4via6, optional
  Ethernet/SNMP, authentication/timeouts, backups, CPU/temperature and opt-in
  firmware updates. WiFi modem sleep remains OFF by default in this fork.

## Exact build and device validation

Target: ESP32-S3 N16R8, 8 MB octal PSRAM, existing 4 MB partition layout.
Pinned PlatformIO Espressif32 6.13.0 / ESP-IDF 5.5.3, 31 sockets.

The initial local compiler write failure was diagnosed as Windows Controlled
Folder Access through its event log. A complete build succeeded in a temporary
directory without modifying Defender; a second normal workspace build also
succeeded after the owner restored access. The installed candidate is the
first build below, not a later image with different build metadata.

- Installed image: 1,711,520 B; application use 1,711,120 / 1,966,080 B;
  static RAM 85,908 B. An alternative workspace build also fits, but is not
  substituted for the actual tested image.
- Authenticated Tailnet OTA was explicitly authorized, uploaded once,
  accepted, and the exact candidate booted in 65 seconds. Eight saved-setting
  groups were compared in memory and remained unchanged; no private snapshot
  was written. No NVS erase, factory flash or identity reset.
- Exact ELF ntfy ENTRY frames: worker 496 B, polling 768 B, info 1,488 B,
  command 320 B, publish 496 B, state save 512 B, alert 32 B and batch read
  48 B, all within the existing budgets. A raw ELF instruction decoder retains
  these checks when Windows objdump does not decode instructions.
- Fifteen protected GET endpoints reject anonymous access and load after
  login. The new TX diagnostic rejects nonboolean input, switches to the
  copying path live and restores the original copy-free path. Actual Tailnet
  HTTP replies were received on both paths. SNMP remains OFF.
- Served UI, including the locally bundled backup crypto library, matches
  the embedded source exactly. No UI feature/style replacement is made.

The first combined integration/ntfy check observed a control-plane reconnect:
the strict connected-state assertions failed while Tailnet HTTP and the VPN
data path stayed usable. The board did not reboot and control registration
recovered automatically. The original ntfy command policy was restored, with
no command errors reported. This observation is retained rather than hidden
as a clean first run; subsequent observation/test results are recorded below.

After recovery, a 300-second observation through authenticated Tailnet HTTP
reported no control-state transition, reboot or WiFi/MQTT loss (minimum internal
free heap 16,683 B). A repeated strict 180-second integration check completed
32 samples without reboot or disconnection (minimum 16,535 B). Concurrent ntfy
HTTPS tests completed three info commands and exact-version replies in 184
seconds without a restart; minimum ntfy stack reserve was 4,388 B and internal
heap 16,479 B. The original command policy and TX path were restored. These
bounded successful repeats do not erase the initial reconnect observation.

## Offline regression coverage

The previous suite and new real-C upstream fixtures pass: replay arithmetic,
key/handshake lifetimes, actual X25519 masking, strict decoding/Noise bounds,
coordinator EOF/partial stalls, DERP TLS configuration/failure policy, TCPIP
execution and the authenticated TX diagnostic. Existing ntfy, startup/AP/
session, routing, SNMP, both forwarding paths and OTA regressions remain.
Thirty-eight TCP/UDP scenarios execute the pinned SDK's real IPv4/NAPT/pbuf
path. Twenty-nine browser scenarios pass. Feature guards compare the old
baseline and the entire previously published 1.12 control surface.

The custom microlink merge commit is
`1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`, with the upstream v0.1.38
dependency as its second parent. Existing custom changes are retained.

Pattern scans reported zero findings in current source/submodule and 1,451
historical blobs before the new integration commit. This is not proof of the
absence of every secret or vulnerability. CI adds sanitizer coverage; its
actual result must be checked, not inferred from local unsanitized tests.

## Local artifacts

The prepared package contains the exact installed `firmware.bin`, a merged
`firmware-factory.bin` with a blank NVS region, guided Windows update/clean
scripts, bundled esptool, checksums and original component license notices.
CRC, packaged payload hashes, credential patterns and exact OTA bytes pass.
The clean-install script is not physically exercised. Do not upload the
factory image through the Web UI. Manual OTA preserves settings.

OTA SHA-256:

`38e2eacd583e4810c8b154b3ade6fd03fb7abee1fb735af257a92b088e43a07a`

Windows ZIP SHA-256:

`6a5ece0e19944c2d9a6796c06f575df4d02e9f2ed72cde8ec4503db52c52f774`

The tested ELF is retained locally for future crash decoding, not distributed
as a public artifact. No new public firmware release is implied by this source
record; stable downloads and update-channel selection remain unchanged until
an explicitly published compatible release exists.

## Limits

No fresh physical Ethernet, NAS wake/recovery, Home Assistant frontend,
Internet exit throughput, certificate-substitution, forced-WAN-roam or
multi-day soak result is claimed. Existing credentials/policies are preserved;
ntfy command topics and MQTT brokers must still be protected by their operator.
Web administration is HTTP on a trusted LAN or encrypted tailnet, not for
public Internet exposure. Stable/beta are release labels, not certification.
