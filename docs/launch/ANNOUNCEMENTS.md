# Launch drafts (not published)

Drafts for the owner to review and post. Tone: technical, no superlatives, no
claims beyond what is tested. Replace `<release>` with the published tag and
attach the social preview (`assets/brand/png/social-preview.png`). Post only
where community rules allow project announcements.

---

## GitHub release announcement

**ESP32 Tailnet Gateway — Mattboxx Edition `<release>`**

*One ESP32. Multiple Tailnet roles. Enable only what you need.*

This edition of Csontikka's esp32-tailscale-subnet-router gets a new name and
a focus: the **Selective LAN → Tailnet Service Gateway**. A device on your LAN
that cannot run Tailscale can now use one specific service on your tailnet —
an MQTT broker, a NAS web UI, an SSH host — through an ESP32-S3, restricted to
the source address you choose.

New in this release: a guided "What do you want to do?" start, simple and
advanced modes, a Web UI that works on phones, English/Italian/Spanish/Chinese,
destination tests and Service watch, a recovery access point, and a safer
updater. Settings are kept when updating.

Limits: microcontroller throughput (control and telemetry, not video), IPv4
TCP/UDP service rules, community firmware and not an official Tailscale client.
Read the release notes for exactly what was and was not tested.

Updating from 1.13 or older after the repository rename: install this release
once by hand (System → Firmware → `firmware.bin`); from then on the updater
works again.

---

## ESP32 community (forum / Reddit r/esp32)

**Title:** ESP32-S3 firmware that lets LAN devices reach one Tailscale service without a client

I maintain a fork of an ESP32-S3 Tailscale subnet router and turned it into a
small, selectable gateway. The main use case: a LAN device that cannot run
Tailscale gets access to one TCP/UDP service on the tailnet (rule = listen port
on the ESP32 → tailnet host:port, restricted to a source CIDR). It also does
subnet routing, an IoT access point, exit node, Wake-on-LAN and optional
MQTT/HA. ESP-IDF 5.5.3, N16R8 board, userspace WireGuard via microlink.

Honest numbers: it is an MCU — fine for control traffic and SSH, not for bulk
transfers; the candidate has not been benchmarked. Feedback on other ESP32-S3
boards is very welcome (there is a hardware report template).

Links: repository, website, release.

---

## Tailscale / Headscale community

**Title:** Selective LAN → tailnet port forwarding on an ESP32 (works with Headscale)

Community project, not affiliated with Tailscale. For sites where you cannot
install a client on a device: an ESP32-S3 joins the tailnet and exposes one
tailnet service per rule on its LAN address, with a mandatory source CIDR.
The remote peer sees the ESP32's identity, so your ACLs still apply. Tested
against hosted Tailscale; Headscale ≥ 0.26 supported (public-CA HTTPS).
Tailnet lock is not supported. Policy enforcement is not claimed to match the
official client.

---

## Home Assistant community

**Title:** ESP32-S3 Tailnet gateway with MQTT Discovery (rule switches, destination tests, WoL)

If your Home Assistant must reach a broker or device at another site over
Tailscale — or the other way round — this ESP32-S3 firmware can bridge it.
Optional MQTT Discovery creates switches for each LAN → Tailnet rule (bound to
the rule's token), destination-test buttons, Wake-on-LAN buttons and status
sensors. Everything is off by default; routing does not depend on MQTT.

---

## Homelab community (r/homelab, r/selfhosted)

**Title:** A small ESP32-S3 board to wake and check your NAS over Tailscale, plus selective LAN → tailnet access

A separately powered ESP32-S3 stays on your tailnet while the NAS is off:
it can send Wake-on-LAN, run a bounded check of a known port and report what
it actually observed (a sent magic packet is not proof of power-on). It can
also publish one tailnet service to a LAN device without a client. No cloud,
no telemetry, opt-in updates.

---

## Migration message for existing users

> The project is now **ESP32 Tailnet Gateway** and the repository moves to
> `Mattboxx/esp32-tailnet-gateway`. Old links redirect. Your settings are
> kept. If your device runs **1.13 or older**, its updater cannot follow the
> rename: install the new release once by hand (System → Firmware →
> `firmware.bin`, or `UPDATE_KEEP_SETTINGS.bat`). Back up your configuration
> first. After that, updates work as before.
