# Subnet router (tailnet → your LAN)

Lets tailnet clients reach devices on a network behind the gateway. This is
the reverse direction of the [Service Gateway](SERVICE-GATEWAY.md) (LAN →
specific tailnet services).

1. Tailscale page → **Advertise the AP subnet** and/or **Additional advertised
   subnet routes** (one CIDR per line, e.g. `192.168.1.0/24`). Save; a restart
   may be required.
2. Approve the routes in the Tailscale admin console or on Headscale. The
   device cannot verify approval; the capability list says "route intent".
3. Optional **Source-NAT advertised routes**: forwarded traffic appears to come
   from the gateway, useful when LAN devices have no route back to the
   tailnet. It hides the original tailnet client from LAN devices.
4. On clients: enable "use subnet routes" (`--accept-routes`).

Security: every tailnet identity your ACL allows can reach the whole advertised
subnet. Prefer narrow prefixes and tailnet ACLs; the gateway's local firewall
lists (Firewall page) add a second filter. Throughput is limited by the ESP32.

Related: **Accept peer subnet routes** makes the gateway itself use routes
advertised by other nodes. 4via6 (CONFIGURATION.md) maps overlapping sites.
