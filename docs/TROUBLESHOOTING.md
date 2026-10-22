# Troubleshooting

Work from the bottom layer up and stop at the first one that fails. The
Status page → **Guided setup → Connectivity troubleshooting** runs these
checks for you; each result is evidence about one layer, not a diagnosis of
everything above it.

| Layer | Check | If it fails |
|---|---|---|
| Uplink | Status: uplink address | WiFi credentials, DHCP/static settings; Ethernet build: link and pins |
| Gateway/DNS/Internet | Devices & Recovery → layered checks (opt-in) | Router, resolver; a closed gateway port is not a router failure |
| Tailscale control | Status: Tailscale connected | Auth key, login server (Headscale), clock, uplink |
| Policy authority | Devices & Recovery summary | Wait for a complete control map; data stays closed until then |
| Peers | Tailscale page: online peers | The peer itself, its ACLs |
| Service | Service Gateway rule status | see below |

## Service Gateway rule states

| Status | Meaning | Next step |
|---|---|---|
| `disabled` / `ready_to_enable` | Rule off (destination already tested) | Enable when the exposure is intended |
| `uplink_no_ipv4`, `control_not_ready` | A lower layer is down | Fix that layer first |
| `destination_unresolved` | No Tailnet IPv4 for the destination | Use a current 100.x address or MagicDNS name |
| `mapping_not_installed`, `runtime_error` | Listener not active | Read the runtime error; port conflicts |
| `destination_no_answer` | No TCP handshake in 2 s | Peer online? Service listening? ACL allows this gateway? |
| `source_rejected` | Only rejected LAN packets seen | Client address vs the rule's source CIDR, expiry |
| `destination_reachable` | Handshake works from the gateway | Try the allowed LAN client on ESP-IP:listen-port |
| `service_replied` | Reply admitted for the remote tuple (possibly a test or another rule) | Verify the intended LAN client and application; this is not end-to-end proof |

Press **Test destination** on a rule (works while it is disabled). UDP cannot
be tested by handshake: use the reply evidence and the receiving service.

## Administration

- *untrusted Host without a web password*: open the device by IP address or
  `.local` name, or set a web password.
- *rate_limited* / *Too many failed logins*: the device-wide login budget is
  exhausted; wait the indicated seconds (shared by Web and console).
- *cross-origin write refused*: a page on another site tried to change
  settings; open the Web UI directly.

## Collect evidence

Devices & Recovery → **Sanitized export** produces a local JSON without
names, destinations, IPs, ports, credentials or tokens; attach it when asking
for help. The pre-crash log and SD log stay on the device unless you download
them.
