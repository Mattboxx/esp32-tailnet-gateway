# First-boot setup (captive portal)

A brand-new or factory-reset ESP32 Tailnet Gateway configures itself from a
phone or PC through its own Wi-Fi. There is no default admin password and no
shared default Wi-Fi password.

## When it appears

Only on a gateway with no saved setting at all: no admin password, no home
Wi-Fi, no tailnet auth key and no setup marker. A gateway that was ever
configured, including one upgraded from 1.13, records a marker on its first
boot and never opens the setup network again, even if settings are later
removed. A factory reset erases everything, so the setup returns.

## Steps for the user

1. Power the gateway. Join the open Wi-Fi **ESP32-Tailnet-Setup-XXXX**
   (XXXX: last characters of the gateway's MAC address).
2. The setup page opens by itself on most phones and PCs. If not, open
   **http://192.168.4.1/**.
3. **Pair:** press the **BOOT** button on the board once. Without a reachable
   button, connect USB, open a serial console at 115200 baud and type the
   8-digit setup code printed there every 30 seconds.
4. **Password:** choose the admin password (at least 8 characters).
5. **Wi-Fi:** pick the home network from the scan, enter its password and
   press *Test connection*. The setup Wi-Fi may drop for a moment while the
   radio moves to the home channel; the phone rejoins and the page continues.
6. **Tailnet:** paste an auth key (Tailscale, or Headscale with its URL), or
   leave it empty and join later from the dashboard.
7. **Features:** share the home network as a subnet route, share the
   gateway's own Wi-Fi, offer an exit node, keep the gateway Wi-Fi always on
   or only as a recovery network, its name and password, Simple or Advanced
   interface.
8. **Finish:** the gateway saves everything and restarts (about 30 seconds).
   Reconnect to the home Wi-Fi and open the address shown, or the tailnet name.

If the home Wi-Fi later disappears, the gateway opens its own **protected**
Wi-Fi (the name and password chosen in step 7) after 60 seconds; this
recovery network is never the open setup network.

## Security design

| Threat on the open setup Wi-Fi | Protection |
|---|---|
| Someone nearby configures the gateway first | Pairing requires physical presence: the BOOT button or the console setup code. One pairing at a time; a second device is refused and the page says so. Five wrong codes lock the code until a restart. |
| Passive capture of passwords and keys | Browser and gateway agree on a session key with X25519; every setup request is sealed with AES-256-GCM (session id and an increasing sequence number authenticated). The admin password, Wi-Fi password and auth key never cross the radio in clear. |
| Replay or tampering with setup requests | Sequence numbers must increase; a forged or reused message is refused without side effects. |
| Using the open network to reach the home LAN | The setup network forwards nothing: only ARP and IPv4 to the gateway itself (or DHCP broadcast) pass, and NAT is not enabled. |
| Other APIs while unconfigured | Every other API answers 403 until setup is finished. |
| Power loss while saving | The protected access point and the admin password are saved first; an interrupted save either restarts the setup or leaves a password-protected gateway with its protected Wi-Fi. |
| Restart before Finish (power loss, crash, unplugging) | Nothing typed in the wizard is stored before Finish: the Wi-Fi test runs from RAM only, so the gateway restarts into the same open setup with a new code. Pair again and repeat the steps. |

**Residual risk:** an attacker who is present during the few minutes of setup
can run a fake access point with the same name and serve a modified page; no
browser-only design can prevent that without a pre-shared secret. Set up the
gateway where you can see it, and check the steps above. The setup code and
the BOOT button prove presence; they are not printed anywhere else.

## Technical reference

- Firmware: `main/first_boot.c` (HTTP, AP, captive DNS, BOOT watcher),
  `main/first_boot_core.c` (pairing, sealing, checks, AP isolation),
  `components/dns_relay` (captive answers), `main/main.c` (setup SSID, trial
  association), `main/netif_hooks.c` (AP isolation hook).
- API (setup mode only, only through the setup AP): `GET /api/setup/state`,
  `POST /api/setup/begin` `{client_pub}`, `POST /api/setup/claim` `{sid, code}`,
  `POST /api/setup/apply` `{sid, seq, iv, ct, tag}` with sealed
  `{action: "wifi_test" | "finish", …}`.
- Key: SHA-256("mattboxx-tailnet-gateway-setup-v1" ‖ shared ‖ gateway public
  key ‖ browser public key). AAD: session id ‖ big-endian sequence.
- Tests: `tools/test_first_boot.py` (actual C code with Python cryptography),
  `tools/test_setup_crypto.cjs` (page crypto against Node),
  `tools/test_first_boot_ui.cjs` (wizard end to end, 4 languages, layouts).
- Hardware: the board used for development is configured and must not be
  erased, so the open-AP flow itself is not yet qualified on hardware; a spare
  or factory-reset board is needed (see QUALITY-GATE).

## Website update for Codex

Replace the first-start instructions on the site's getting-started page with
the user steps above (join *ESP32-Tailnet-Setup-XXXX*, captive page or
192.168.4.1, BOOT button or console code, wizard, restart). Mention that there
is no default password, that the setup network is open only on an
unconfigured gateway, and the residual risk sentence. Do not change it before
the firmware containing this feature is released.
