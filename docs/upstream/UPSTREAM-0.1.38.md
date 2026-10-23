# Published upstream v0.1.34–v0.1.38 alignment

October 20, 2026. Custom candidate: `0.1.38-Mattboxx-1.13-dev.1`.
The previously published stable release remains unchanged.

## Pinned source and credit

| Release | Router commit | microlink commit |
|---|---|---|
| v0.1.34 | `fff049438493442206c1ee75f38317ed4cd5705b` | `6fe1cc8c79f481fe9c11c86521b0628ba3665076` |
| v0.1.35 | `a9fbf2d53c21d111ab4371f4634fe1000adc81af` | `eb63b97073e529d57bc9c1deaeea25ac304034e5` |
| v0.1.36 | `801c8d6203a61f038fae495bdc5f622e58019d61` | `21929f5e47864b747b7c34bc92b47bca65891793` |
| v0.1.37 | `dc634eb44b12969dcd50b08b6d29027d9e267035` | `ee47277c449bdd49a9af96e92e73b57fb50bb55c` |
| v0.1.38 | `42ec1081c5abb2166c429b038373aa13fa268bc0` | `a85e8c42ee2ed3223f8c3bd3766fc37af1985384` |

The full microlink range after `2c796e3b14872b94fb2c54102affaacb1cc4a77b`
is merged into the existing custom dependency, not substituted for it.
Custom merge: `1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`.
Original work remains credited to Csontikka's router, Cameron Malone,
Csontikka/microlink, contributors and the other forks identified by upstream.
No newer untagged upstream runtime commits are included.

## Integration decisions

| Published improvement | Treatment in this fork |
|---|---|
| DERP relay TLS verification | CA bundle and hostname checking by default, including DERPMap CertName/InsecureForTests compatibility and fail-closed CA-attach errors. A self-signed relay previously accepted without checking now needs a supported trust configuration. |
| WireGuard replay/key/handshake correctness | Full 64-bit replay arithmetic, rejection limit, authentication before state updates including keepalives, current/previous/next key lifetimes, handshake expiry, session index collision detection, initiation timing, short decrypted-IP checks and X25519 high-bit handling. Keep fork 4via6 and direct/relay reply hooks. |
| WireGuard send-counter serialization | Import the upstream mutex around counter read, encryption and increment, including initialization at interface setup. |
| Strict peer key and Noise reply decoding | Import exact key validation, minimum header allocation and exact IK reply length checks. No partially decoded peer keys are admitted. |
| Dead/stalled control sessions | Import EOF/GOAWAY/RST_STREAM/END_STREAM handling and partial-frame stall deadlines. These are not application-level HTTP timeouts. |
| TAI64N persistence | Keep a monotonic saved timestamp floor on both synchronized and unsynchronized boots. |
| Correct, sticky relay measurement | Drain STUN replies during the sweep, use repeated samples and hysteresis. Default measurement ON for unset settings, retaining explicitly saved override/region/threshold choices. Show up to 32 region measurements instead of 16. |
| Relay region actually in use | Correct PreferredDERP, protect the measured choice from a control-plane echo, request control publication and reconnect the relay when needed. |
| Silent peer re-handshake | Arm recovery only for unanswered data and re-handshake after 15 seconds; authenticated traffic disarms it. Keep fork last_direct_rx separate from relay activity. |
| WG netif lifecycle on TCPIP thread | Import v0.1.38's completion-waiting esp_netif_tcpip_exec for init, bring-up, output PCB and teardown. Do not retain v0.1.37's asynchronous-free regression. |
| Timed-out stop | Import ERROR/timeout state rather than admitting another start over surviving workers; retain custom startup barrier, largest-stack-first ordering and partial-start rollback. |
| Router instance withdrawal | The fork already never frees/replaces a published instance live: disconnect is restart-based, and an instance is published only after successful startup. Keep that stronger existing lifetime policy instead of introducing raw-pointer live teardown. The imported WG worker separately withdraws wg_netif before destruction. |
| SD recorder lifetime guard | Guard reads and detach with a checked, statically allocated mutex; no extra allocation on uplink recovery. Recording remains local. |
| Copy-free WireGuard TX | Import SPIRAM pbuf allocation/output and profiling. Expose wg_tx_pkts, wg_tx_us and wg_tx_copyfree in authenticated diagnostics. Add upstream /api/debug/wg-tx, requiring a password session, strict boolean inputs and a lifecycle lease; propagate failures without resetting counters. This diagnostic switch is runtime-only. |
| Upstream README/performance/release text | Attribute upstream results rather than imply a fresh benchmark here. Retain custom quick start, hardware limitations, license/support notices and release-channel rules. |

## Preserved custom behavior

AP-side forwarding and independent LAN-to-Tailnet rules/source restrictions,
MagicDNS, configurable Web UI port, optional AP/auto-off, named WoL, MQTT/HA,
ntfy, 4via6, IPv4 exit controls, hardware-dependent Ethernet, authentication/
timeouts, encrypted backups, read-only SNMP, CPU/temperature, diagnostics,
opt-in updates and local-only Ko-fi support are retained. No external log/crash
upload, usage telemetry, hard-coded public DNS or forced update polling is
restored. Saved credentials/identity are not bundled in the firmware.

## Verification scope

`test_upstream_038.py` compiles real C fragments with synthetic dependencies:
64-bit replay bounds, independent key/handshake expiry, actual X25519 high-bit
equivalence, strict key parsing, EOF/partial stalls, Noise reply bounds, DERP
TLS configuration/failure policy, synchronous TCPIP callbacks and the new
authenticated diagnostic handler. Tests do not replace live TLS validation,
real traffic through rekeys or a long-duration roam/throughput test.

The existing feature-preservation, automation browser, ntfy, lifecycle,
forwarding, routing, SNMP, updates and pinned-lwIP regressions remain. Full
build/device/package observations belong in the candidate release record,
not inferred from upstream's reference-board measurements.

Primary comparison: [router v0.1.33…v0.1.38](https://github.com/Csontikka/esp32-tailscale-subnet-router/compare/v0.1.33...v0.1.38).
