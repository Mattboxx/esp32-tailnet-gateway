# ntfy transport audit — Mattboxx 1.10 development

## Confirmed issues

The pinned ESP-IDF 5.5.3 HTTP client automatically follows redirects unless
disabled. Its redirect path changes the URL without removing manually set
Authorization headers or POST bodies. ntfy previously used that default for
both publishing and command polling. A configured server/proxy returning a
redirect could therefore send the bearer token and notification contents to
another host or downgrade HTTPS to HTTP. It could also change the source of
remote commands. This does not imply the official ntfy server is malicious.

The token-header allocation result was also ignored. A header allocation
failure could issue a request without the user's configured credentials.
Token control characters were not rejected before HTTP header construction.

## Fix and compatibility

- Both ntfy clients explicitly disable automatic redirects. HTTP 3xx fails;
  no redirected request, reply-body execution or cursor advancement follows.
- Use the final ntfy server URL, including any self-hosted path prefix. A proxy
  must forward the request rather than redirect the device to another endpoint.
  The UI now explains this. There is no unsafe redirect fallback.
- Token values must be printable ASCII without whitespace/control characters.
  Invalid values fail before network access; tokens remain write-only in the UI.
- A failed Authorization-header setup aborts the request, frees its resources,
  and reports failure. An intentionally empty token still supports anonymous
  topics. Explicit local HTTP setups remain supported with the existing warning.
- Existing MQTT, WOL, ntfy commands/alerts and update policies are unchanged.

## Evidence and limitations

`tools/test_ntfy_transport.py` compiles the actual publish, poll, validation
and authorization functions with real cJSON and deterministic HTTP fixtures.
The pre-fix code failed the foreign-redirect regression; the corrected code
rejects 301/302/303/307/308, 401/403/500, header-allocation failure and invalid
tokens. Successful direct publishing/polling and anonymous topics still work.
The CI suite runs this fixture with address/undefined-behavior sanitizers.

The transport fixture does not implement real TLS or contact a live server.
Passing it does not prove that all firmware bugs or security issues are gone.
Hardware validation should include a direct HTTPS test notification, an info
command, WOL and a self-hosted redirect refusal, using the exact candidate build.
