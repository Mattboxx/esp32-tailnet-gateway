# Headscale

> **1.14 development preview.** This guide includes unreleased features; it
> does not imply a new firmware download. Public stable remains
> [Mattboxx 1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13).


The gateway joins a self-hosted [Headscale](https://github.com/juanfont/headscale)
control server the same way as hosted Tailscale; only the login server differs.
Compatibility with every Headscale version is not verified automatically.

1. On the Headscale server create a user and a pre-auth key (prefer an
   expiring, reusable-only-if-needed key, ideally tagged).
2. Web UI → **Tailscale**: set **Login server** to your server, e.g.
   `https://headscale.example.com` (also `host`, `host:port`, `http://...`).
   HTTPS certificates are validated against public CAs only; a private CA is
   not accepted.
3. Paste the pre-auth key in **Auth key**, choose a hostname, enable, save.
4. Approve advertised routes or the exit node on the server
   (`headscale routes ...` / your admin UI); the device cannot see approval.
5. Status → Tailscale connected; the capability list shows `headscale`
   configured. Control connection is not proof that peers or services work.

Notes: a DERP map comes from your server; if it serves none, only direct paths
work. **Reported client version** is an optional compatibility override and
does not add capabilities. ACL/policy features are subject to the
[policy compatibility boundary](../SECURITY.md#tailnet-policy-compatibility-boundary).
