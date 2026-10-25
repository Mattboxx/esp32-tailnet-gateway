# Dynamic DNS

Keeps a public name (for example `myhome.duckdns.org`) pointing at your home
internet address, so you can reach a service **you** publish on your router
(a port forward you set up yourself). The gateway only updates the name:
nothing is opened or forwarded on the router.

Network → Internet → **Dynamic DNS**. Off by default; while off there is no
timer and no task.

## Providers

| Provider | You enter | Notes |
|---|---|---|
| DuckDNS | sub-domain(s) without `.duckdns.org` (up to 5, comma separated) and the token from duckdns.org | Without a known address DuckDNS uses the address the request comes from. |
| Cloudflare | full record name (`home.example.com`), zone id (32 hex characters, dashboard → domain → Overview) and an API token limited to *Zone → DNS → Edit* | The A record must already exist; the gateway only changes its address. |
| Other | an HTTPS update URL, optionally with `{ip}` | `{ip}` is replaced by the public address; without it the provider uses the request's source address. Kept like a password. |

Tokens and update URLs are write-only: the page shows that one is saved,
never its value. Requests use HTTPS with certificate verification only.

## Where the address comes from

1. Tailscale's own connectivity check (the public address its STUN probe
   sees). No extra lookup service.
2. For Cloudflare, when Tailscale has not seen it: Cloudflare's own trace
   endpoint (`www.cloudflare.com/cdn-cgi/trace`), so no third party is added.
3. DuckDNS and URLs without `{ip}`: the provider takes the address the
   request comes from.

## When it updates

When the address changes, otherwise once a day; every 30 minutes while the
address cannot be seen. Failures back off from one minute up to an hour. The
card shows the public address, what the name points at and when it was last
updated; *Update now* forces one. Successes and the first failure of a run
are written to the event history (and so can be sent by Telegram or email).

## Limits

- IPv4 (A records) only.
- Behind carrier-grade NAT (many mobile and some fixed lines) a public name
  cannot reach your router at all; use the tailnet instead.
- A name is not access: the service still needs your own port forward and
  its own protection. Prefer reaching services through the tailnet.

Source: `main/ddns.c` (core host-tested by `tools/test_ddns.py`).
