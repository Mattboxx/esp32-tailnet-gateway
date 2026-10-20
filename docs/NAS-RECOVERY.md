# NAS and homelab recovery checklist

This firmware can provide a management node independent of your NAS operating
system. It is not file recovery, IPMI/KVM, a power relay, or fully out-of-band
management. A stable release channel does not certify every NAS or network.

## 1. Give the recovery node a chance to stay online

- Use the published ESP32-S3 N16R8 image only on matching hardware with 8 MB
  octal PSRAM. [Download the stable release](../../../releases/latest).
- Power the ESP independently of the NAS. A NAS USB port that loses power
  during shutdown defeats the purpose. Consider backup power for the ESP,
  router/AP and modem together if power failures are part of your scenario.
- Keep the WiFi/router, uplink and Internet available. The ESP uses 2.4 GHz
  WiFi on the reference board; it cannot bypass a failed home router or ISP.
- Do not make the only command path depend on a broker, Home Assistant or
  notification server hosted exclusively on the NAS you are trying to wake.

## 2. Configure and test remote administration

Follow the [quick start](../README.md#quick-start), join your WiFi and enroll
the ESP on your Tailscale/Headscale network. Keep the Web UI password enabled.
Use a trusted LAN or encrypted tailnet access; do not publish the HTTP Web UI
through an Internet router port forward.

From another authorized tailnet device, open the ESP's tailnet address and
log in. Repeat from a phone on mobile data, with home WiFi disabled. Configure
and approve advertised subnet routes only if you need access to other LAN
devices; opening the ESP's own UI does not require advertising your LAN.
Tailnet access rules and route approval remain under the operator's control.

## 3. Add a compatible Wake-on-LAN target

Enable WoL according to the NAS/PC manufacturer's instructions. Support can
depend on model, Ethernet adapter, firmware, sleep/shutdown state and standby
power. An unplugged device cannot be woken by a magic packet.

In Automation, save a named WoL device with its network adapter MAC address,
the correct LAN broadcast address and destination port. Keep the ESP and
target on a network where that broadcast can reach the target; routing/VLAN
boundaries can prevent delivery. First verify WoL locally, then repeat it
through the ESP's tailnet UI. An accepted send means a packet was sent, not
that the target necessarily woke or finished booting.

Do not hard-power-off a working NAS to test this. Shut it down cleanly,
verify that the ESP remains reachable, send WoL once and observe whether
the NAS boots and its service returns. WoL is not a general remedy for a
frozen OS, a failed disk, a damaged bootloader or a lost power supply.

## 4. Choose optional automation without creating a circular dependency

- MQTT/Home Assistant discovery exposes availability, controls and saved WoL
  buttons. If the broker or HA server runs on the NAS, those functions may
  disappear while it is off. Keep direct tailnet administration as a separate
  path, or host the broker/controller independently.
- ntfy can provide optional alerts, info replies and WoL commands. It must be
  enabled and its command policy configured. Protect command access with
  the server/topic authorization model; enabling command reception on an
  unprotected topic gives its publishers control of those commands.
- AP gateway policy is separate from the NAS use case. The ESP can join your
  uplink WiFi while its client AP is disabled. Test the chosen recovery policy
  before relying on it away from home.

## 5. Rehearse before leaving home

Record the exact firmware, board and NAS model, WoL configuration, independent
power source and observed result. Test from outside the LAN, with the NAS
cleanly shut down, then confirm access to the actual NAS service after boot.
Re-test after changing router, VLAN, NAS standby or tailnet access settings.
Do not confuse a successful browser request or magic-packet send with a
completed end-to-end recovery test.

There is no custom-release NAS-model compatibility matrix yet. Contributions
should report real results rather than infer support from a manufacturer name.
When sharing logs/screenshots, remove addresses, SSIDs, MACs, tailnet/device
names, topics, credentials and other identifying details as appropriate.

## Other gateway uses

The firmware also retains Tailnet-to-LAN/AP subnet routing, an optional WiFi
gateway for devices without a VPN client, separate AP-side port maps,
LAN-to-Tailnet TCP/UDP service forwarding, IPv4 exit-node controls, diagnostics
and opt-in firmware updates. These are independent features, not requirements
for the basic named-WoL use case. An ESP32 is a small remote-admin/IoT node,
not a high-throughput NAS data-transfer router.

Original work: [Csontikka's router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink), originally by Cameron
Malone. This is the Mattboxx community fork, not an official Tailscale client.
