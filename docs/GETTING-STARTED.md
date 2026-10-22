# Getting started

Who it is for: anyone setting up an ESP32 Tailnet Gateway for the first time.
You need an ESP32-S3 N16R8 board, a USB data cable, a 2.4 GHz WiFi network and
a Tailscale account or a Headscale server. Plan about 20 minutes.

## 1. Flash it — no build tools required

Download the latest
[Windows flashing ZIP from the latest stable release](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/latest),
connect the ESP32-S3 over USB and run one of the included guided batch files:

- `UPDATE_KEEP_SETTINGS.bat` updates an existing installation without erasing its configuration;
- `CLEAN_INSTALL_ERASE_ALL.bat` performs a fresh installation and removes every old setting.

The release also provides `firmware-factory.bin` for other flashing tools and
`firmware.bin` for the local web updater.

## Build from source instead

```bash
git clone --recurse-submodules https://github.com/Mattboxx/esp32-tailnet-gateway
cd esp32-tailnet-gateway

# PlatformIO (recommended)
pio run -e esp32-s3 -t upload

# …or ESP-IDF (>= 5.5.3)
idf.py set-target esp32s3
idf.py build flash monitor
```

> The web assets are embedded into the firmware at build time from
> `main/index.html`, so a single flash carries the whole UI.

## 2. First-time setup

On first boot the device brings up its own access point:

- SSID: **`ESP32-TSR-Setup`** (builds before v0.1.18: `myssid`),
  password: **`mypassword`**
- Connect to it and open **http://192.168.4.1** — set an admin password
  there, then rename the AP to your liking.

<div align="center">
<img src="images/login.png" alt="First-run admin password" width="46%">
</div>

## 3. Join your WiFi

On **Network → Access Point / Uplink networks**, point the device at your
existing 2.4 GHz network and (optionally) rename the AP it broadcasts.

<div align="center">
<img src="images/network-ap_v2.png" alt="Access Point configuration" width="80%">
</div>

## 4. Enrol on your tailnet

This is the one step with a couple of non-obvious Tailscale details — do
them once and the device stays on your tailnet for good.

### 4a · Create a Tailscale auth key

Log in to the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
→ **Settings → Keys** and click **Generate auth key…**.

<div align="center">
<img src="images/tailscale-keys-page.png" alt="Tailscale admin — Keys page" width="80%">
</div>

Fill in the dialog:

<div align="center">
<img src="images/tailscale-auth-key-create.png" alt="Generate auth key dialog" width="70%">
</div>

| Option | Value | Why |
|---|---|---|
| **Description** | `esp32-router` | so you can find it later |
| **Reusable** | ✅ On | re-flash without regenerating a key |
| **Ephemeral** | ❌ **Off** | ephemeral nodes get garbage-collected when offline — bad for a device that reboots |
| **Pre-approved** | ✅ On *(if your tailnet uses device approval)* | lets the device join without a manual click |
| **Tags** | `tag:esp32` *(optional)* | handy for ACL targeting |
| **Expiration** | 90 days *(max)* | Tailscale caps this — you make the node **permanent** in 4c below |

Copy the key (it starts with `tskey-auth-…`).

### 4b · Paste it into the device

On the device's **Tailscale** tab, paste the auth key, set a **hostname**,
and list the **subnet(s) to advertise** (your AP subnet is offered
automatically). Pick an **exit node** here too if you want AP clients to
egress through it. Save — the device registers with your tailnet on its
next connect.

<div align="center">
<img src="images/tailscale_v2.png" alt="Tailscale configuration and peers" width="88%">
</div>

> **Approve the route.** A newly advertised subnet shows up in the Tailscale
> admin (Machines → your device → **Edit route settings**) and must be
> **approved** before peers can use it. And if you later change the AP subnet,
> re-approve the new route there — the old approval stays but no longer matches,
> so the subnet silently becomes unreachable until you do.

> **Reaching the *uplink* LAN (not just the AP subnet).** To expose the network
> the device is connected to (its STA/uplink side), advertise that subnet too and
> turn on **Source-NAT advertised routes**. That masquerades tunnel→LAN traffic to
> the device's own uplink IP (Tailscale's `--snat-subnet-routes` default), so
> upstream hosts can reply without a route back to the tailnet. Without it, the
> upstream router would need a static route (`100.64.0.0/10 → this device`).

> **🔑 Auth key vs. node key — read this once**
>
> - The **auth key** (`tskey-auth-…`) is a *one-time ticket*: the device uses
>   it only on first registration. After that it has its own private **node
>   key** (stored in NVS) and no longer needs the auth key — so it's fine if
>   the auth key later expires.
> - The **node key** is the device's long-term identity, and Tailscale expires
>   it after ~180 days by default. When it expires the device drops off the
>   tailnet — exactly what you *don't* want on an unattended sensor.
>
> So once the device shows up in your tailnet, **disable its node-key expiry**
> (next step). Skip it and everything looks fine for months, then the device
> silently falls off and you won't know why. Do it for every device you flash.

### 4c · Disable node-key expiry (do this — always)

1. Open the [Tailscale **Machines** page](https://login.tailscale.com/admin/machines).
2. Find the new `esp32-router` entry.
3. Click the `⋯` menu → **Disable key expiry**.

<div align="center">
<img src="images/tailscale-disable-key-expiry.png" alt="Tailscale admin — Disable key expiry" width="80%">
</div>

4. **Reboot the device** (Reboot on the **System** tab, or power-cycle). The
   expiry status is only re-fetched on a fresh control-plane login, so a plain
   reconnect isn't enough.

That's it — remote tailnet peers can now reach the IoT devices on the AP
subnet, and those devices can use the tailnet (and any exit node you picked).

## 5. Add your first Service Gateway rule

Follow the [Service Gateway guide](SERVICE-GATEWAY.md): give the ESP32 a fixed
LAN address, add a rule with a single-device source (`/32`), run **Test
destination**, then enable it. Rules start disabled.

## Verify

- Status shows the uplink connected, Tailscale *Running* and peers listed.
- `tailscale ping <esp-hostname>` from another node answers.
- The rule card shows *installed* and its accepted counter grows when the LAN
  client connects.

## Common problems

See [Troubleshooting](TROUBLESHOOTING.md). Most first-day issues are an
unapproved subnet route, node-key expiry left enabled, or a destination peer
whose ACL does not allow the ESP32.

## Security

Set an admin password before joining any shared network, and administer the
device from a trusted LAN or over the tailnet: the local Web UI is HTTP.
