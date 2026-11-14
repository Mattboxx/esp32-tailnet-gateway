# ntfy

Optional push notifications and a few commands through an
[ntfy](https://ntfy.sh) server (public or self-hosted). Technical transport
notes are in [NTFY-TRANSPORT.md](NTFY-TRANSPORT.md).

## Setup

Automation → **ntfy**: server URL, topic and, recommended, an access token.
**Send test** confirms delivery to the server only.

## Messages (each opt-in)

- Tailscale stays disconnected while the uplink works (after the delay).
- System events: gateway started (firmware, reset reason), Tailscale restored
  after a delivered alert, firmware update available (never installed).
- Health Monitor check down after repeated failures.
- Smart Recovery results; temporary service access closed; Service watch
  "no TCP answer" and recovery.

## Commands (topic messages)

Only when **commands** are enabled, optionally only while Tailscale is down:

| Message | Effect |
|---|---|
| `info` | status reply (private details only if *include private details* is on) |
| `wol <saved device name or MAC>` | WoL to a saved device (direct MAC only if allowed) |
| `recover <name>` / `check <name>` | Smart Recovery / check, when Remote commands is set to *Info, Wake-on-LAN and verified recovery* |

**Devices & Recovery → Notify manual results and new outages** enables
the completion message for a saved device. Set a local target, answering TCP
port and timeout (5–600 seconds) in its profile. Use `recover NAME` for a
verified wake and `check NAME` for a reachability check without waking the
device. The acknowledgement means the job was accepted. ntfy works with
Tailscale disabled if the gateway can reach the ntfy server and the device.

Anyone who can publish to the topic can send commands: use a private topic
and a token with write access restricted to you. Replayed message IDs are
ignored after a restart.
