# Security Policy

## Tailnet policy compatibility boundary

This firmware uses third-party microlink, not official tailscaled. The pinned
parent used by stable 1.13 and development dev.1 did not apply MapResponse
`PacketFilter`/`PacketFilters` service permissions to decrypted traffic. IPv4
AllowedIPs/peer pruning were not a substitute; IPv6 source ownership also
lacked an equivalent check. These are confirmed source findings, not a claim
of a successful live unauthorized-access experiment.

Local **1.14-dev.2** adds a bounded, fail-closed authorization gate before
translation/queueing, fresh-session peer/source/destination checks, named
filter updates and exact outbound return flows. It has **not been published
or installed on the reference ESP**. Its conservative protocol subset,
fragment/ICMP limitations and required real-client tests are documented in
[the authorization record](docs/TAILNET-AUTHORIZATION.md). Do not assume
full official-client policy parity. Local STA/AP ACL tables and a LAN rule's
source CIDR remain separate controls, not identity authentication.

Use service authentication, controlled LAN access and destination-side policy;
do not expose sensitive management services on the assumption that every
tailnet grant is enforced by this client. Broader compatibility, two-real-client
tests and hardware resource/soak qualification remain P0 release gates.

## LAN → Tailnet forwarding boundary

Each enabled LAN → Tailnet rule deliberately exposes one Tailnet TCP/UDP
service on the ESP32 uplink address. The firmware requires an allowed-source
CIDR, rejects non-CGNAT resolved targets, isolates these mappings from the AP
and WireGuard input interfaces, and rejects listener collisions. Operators
should still choose the narrowest CIDR, authenticate the destination service,
and enforce Tailnet ACLs; this is a gateway, not an application firewall. A
source CIDR is a network filter, not client identity: a hostile device with
access to the same layer-2 LAN may spoof a permitted source address.

## Exit-node DNS PeerAPI boundary (1.9 development)

Opt-in exit-node server mode starts a separate HTTP DNS server, normally on
TCP 41180 (41181 if the admin UI already uses 41180). This is not a public DNS
service or an admin endpoint: before reading a query/body, it requires the
local tunnel address and a remote address matching a known microlink peer.
Merely using a CGNAT address does not grant access; LAN/AP and native IPv6
requests are denied. Its HTTP listener still consumes bounded resources for
rejected connections, so restrict untrusted networks with firewall policy.
Requests over the tunnel use WireGuard encryption, not HTTPS or the UI login.

Known-peer membership is not per-user authorization. Use tailnet access rules
and the ESP firewall to restrict which trusted peers should use the exit node.
DNS queries deliberately leave through the configured/learned uplink resolver,
using standard unencrypted UDP/TCP DNS; no public fallback is added. The
upstream resolver therefore sees those queries when this feature is enabled.
Message lengths, source endpoint/transaction matching and deadlines are
bounded, but this integration is not a penetration test or a full DNS parser.

## GitHub firmware update trust boundary (1.10 development)

Periodic checks, automatic installation and beta releases default OFF.
The operator may enable them or start a one-off check/install using a real
password-backed session, even if the ordinary UI password gate is disabled.
Only the fixed Mattboxx repository is used; no arbitrary URL or GitHub token
is accepted. HTTPS certificate/redirect checks, release SHA-256 and matching
ESP32-S3/project/version validation precede committing the inactive OTA slot.
The original always-on upstream poller and legacy preferences remain removed.

The GitHub account and release infrastructure are trusted firmware publishers.
A checksum is not a publisher signature: a compromised account could publish
a malicious image with a matching checksum. This does not add Secure Boot or
independent firmware signing. Automatic installs explicitly authorize future
gateway restarts and firmware replacement; beta opt-in accepts less-tested
images. Review releases manually if that risk is unacceptable. No settings,
keys or logs are uploaded, but GitHub sees the source public IP and generic
User-Agent. See [update policy and validation limits](docs/UPDATES.md).

## ntfy transport boundary (1.10 development)

Publishing and command polling do not follow redirects. Use the final server
URL: the configured host remains the only intended recipient of the token and
notification body, and the only source of remote command responses. Reject
token header-control characters and fail before networking if the Authorization
header cannot be installed. Anonymous topics still work when explicitly chosen.
This is not protection against a compromised configured server or public topic.
Use HTTPS and broker-side access controls; explicit HTTP remains unencrypted.
Queued command replies are revalidated after configuration changes and tunnel
recovery. Settings and the endpoint-bound replay cursor share one validated NVS
record; persistence errors defer command execution rather than risk a reboot
replay. Already accepted commands may finish. Legacy settings migrate once;
invalid new state does not silently reactivate the old enabled configuration.
Command polling projects a bounded, fully validated JSON stream instead of
allocating entire cached responses or recursively parsing arbitrary metadata.
Oversized command text, ambiguous duplicate fields, malformed UTF-8, embedded
NUL and excessive nesting cannot execute commands. Authentication/HTTP errors
do not dispatch queued responses; unread complete batches resume by durable ID.
ntfy outage alerts contain only a connectivity warning, never local log tails.
Private info details do not re-enable log uploads. Local Diagnostics remain
available to authorized sessions; explicitly requested info replies can still
include network details under their separate opt-in setting.
See [confirmed issues and regression coverage](docs/NTFY-TRANSPORT.md).

## 1.14 development surfaces (not in a stable release)

Threat-model notes for features added in the development line; offline-tested
only, not hardware-qualified.

| Surface | Who can reach it | Protection | Residual risk |
|---|---|---|---|
| Web/API administration | LAN, AP, Tailnet clients that reach the UI | session cookie (SameSite=Strict), Origin and Sec-Fetch-Site screening on writes, trusted-Host check when no password is set (DNS rebinding), one device-wide failed-login budget shared with the console | HTTP only (no TLS); a LAN attacker on-path can observe sessions; set a password |
| Remote console (TCP) | interfaces selected in its binding | requires the admin password; shares the login budget; "VPN" binding means arrival on the node's tunnel address | plain TCP; prefer the VPN binding |
| Service Gateway rules | LAN clients matching the source CIDR | rules start OFF, exposure confirmation in the guide, optional expiry, binding tokens for remote toggles | a CIDR is not identity; remote peers see the gateway's identity |
| Destination test / Service watch | administrators (and MQTT/HA for the watch switch) | one bounded TCP connect at a time, cooldown, existing worker and socket budget, OFF by default | probes originate from the gateway's tailnet identity |
| MQTT / Home Assistant commands | anyone who can publish to `B/command/#` | strict payloads, binding-qualified rule topics, recovery behind its own switch | authorization is the broker's: use auth, TLS, ACLs |
| ntfy commands and events | anyone who can publish to the topic | commands opt-in, token recommended, replay cursor persisted; events opt-in | public topics are guessable: use a private topic and token |
| SNMP operational rows | SNMP clients allowed by the agent settings | read-only, numeric values only, no targets/identifiers, SET refused | community strings are not strong authentication |
| Diagnostic export | administrators | allowlisted states/counters; no names, destinations, IPs, ports, credentials | review before sharing |
| Ethernet uplink (separate build) | the wired LAN | OFF by default, explicit pins, ESP-bound ACL hooks installed before the interface starts | not physically validated |
| Profiles / guides | administrators | enable-only presets with token-bound preview; guides write through existing validated forms and never read secrets | one rollback level |

Downgrade note: stable 1.13 ignores the lease ledger, so temporary rules become
permanent after a downgrade; see [docs/NVS-KEYS.md](docs/NVS-KEYS.md).

## Reporting a Vulnerability

If you think you've found a security issue in this firmware — for example a
memory-corruption bug in the C code, a way to leak the web-UI password or the
Tailscale auth key / WireGuard keys out of NVS, an ACL/firewall bypass, a
web-UI authentication bypass, or any other concern that affects the safety of a
device running this code — please report it privately rather than opening a
public issue.

**Preferred channel:** use GitHub's [private vulnerability reporting](https://github.com/Mattboxx/esp32-tailnet-gateway/security/advisories/new)
on this repository. This creates a private security advisory that only the
maintainer and invited collaborators can see.

If that isn't available, contact the fork owner through the GitHub profile at
[@Mattboxx](https://github.com/Mattboxx).

Please include:

- A description of the issue and why you think it's a security problem.
- The exact commit / version of the firmware you observed it on.
- Steps to reproduce, if possible — ideally the relevant web-UI / `/api/*`
  configuration or serial-console input and a description of the runtime
  behavior.
- Any logs, crash dumps (coredump), or serial output that illustrates the
  problem.

Reports will be reviewed privately and coordinated before disclosure.

## Scope

This repository is the **ESP-IDF firmware** for the router (AP/STA NAT, web UI,
ACL firewall, DHCP/DNS, etc.). The Tailscale-compatible WireGuard userspace
stack lives in the [microlink](https://github.com/Csontikka/microlink)
submodule — if the vulnerability is in the DISCO/DERP/magicsock/WireGuard
protocol handling itself, please consider reporting it there as well, since the
fix will likely need to land in that project first.

## Supported Versions

The current stable release and default `Main` branch receive security fixes.
Development candidates and older releases are not independently maintained.

## Deployment hardening

- Keep the web password gate enabled. Short passwords are accepted for device
  recovery and compatibility, but a long unique password is strongly advised.
  Password verifiers use salted PBKDF2-HMAC-SHA256; older SHA-256 records are
  upgraded automatically after the next successful login.
- Disabling the web password gate intentionally trusts every client that can
  reach the ESP32: ordinary settings, restart, WOL and automation controls are
  then public. Secret export/import, OTA, identity reset and factory reset
  still require a real password-backed session.
- The embedded UI is HTTP-only. Do not forward its configured port to the Internet or an
  untrusted VLAN. Prefer access through a trusted LAN or the encrypted
  Tailscale path, and disable the access point when it is not needed.
- Prefer `mqtts://`, `wss://`, and `https://` transports. If a plaintext local
  MQTT or ntfy server is unavoidable, isolate it on a trusted network and use
  broker/topic ACLs. Anyone allowed to publish commands can operate WOL and
  the exposed router controls.
- Use an access-controlled, unguessable ntfy topic. The optional `info`
  response excludes passwords and tokens. Network topology, peer names/IPs,
  AP-client MACs and WOL MAC/broadcast details require the private-details
  option. Saved WOL device **names are always included**, as an intentional
  convenience; do not put sensitive information in those names.
- SNMP is OFF by default. SNMPv1/v2c community authentication is plaintext,
  not encryption: use a private community, restrict UDP 161 with the firewall,
  and never forward it to the public Internet. It supports reads only, not SET.
  The community is not included in MQTT discovery/state or ntfy replies.

## Review limitations

See [the 1.7 release record](docs/RELEASE-1.7.md),
[the earlier 1.6 release record](docs/RELEASE-1.6.md) and
[the 1.5 review record](docs/REVIEW-1.5.md) for fixes and validation scope.
Pattern-based secret scans and successful compilation are not a penetration
test and cannot establish the absence of vulnerabilities or personal data.
The CI history scan checks fetched, reachable Git objects. It cannot inspect
deleted remote objects, third-party clones or caches, GitHub messages, or the
device's private NVS storage. The HTTP UI and unencrypted flash/NVS boundaries
above remain unchanged.

## Hardware-security boundary

The general-purpose release does not enable ESP32 Secure Boot, flash
encryption, or encrypted NVS. Those features require owner-specific keys and
an irreversible provisioning procedure; enabling them in a universal binary
would either embed a shared secret or risk making boards unflashable. Treat
physical access as trusted. A device-specific hardened build should provision
unique keys, enable Secure Boot and flash/NVS encryption, then retain an
offline recovery copy of those keys.

## History rewrite — 2026-06-01

The git history of this repository was rewritten on 2026-06-01 to remove
development-environment data that had been committed in earlier code comments,
a deleted helper script, and test utilities:

- the maintainer's real Tailscale **tailnet name** and a development **WiFi
  SSID** (replaced with generic placeholders);
- development-network **IP ranges** (replaced with generic RFC1918 examples);
- a development **admin password** that appeared in a since-deleted helper
  script (`tools/verify_routes.py`) — replaced with `REDACTED`.

That password protected only a local development board, but since it was once
public it must be considered **burned** and should be **rotated** on any
affected device. No Tailscale auth keys, WireGuard keys, API tokens, or private
keys were ever committed (those have always been git-ignored).

Because history was rewritten, commit hashes prior to this date differ from any
older clone or fork. Re-clone rather than pull if you have an old copy. The
rewrite is marked by the annotated tag `history-scrub-2026-06-01`.

## Non-affiliation notice

This project is **not** affiliated with, sponsored by, or endorsed by Tailscale
Inc., Jason A. Donenfeld, or the WireGuard project. Please do not report
Tailscale-service or WireGuard-protocol vulnerabilities here — report those to
the respective upstream projects.
