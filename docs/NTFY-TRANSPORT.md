# ntfy transport and persisted-state audit — Mattboxx 1.10 development

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

Command polling also kept using a configuration snapshot after a settings save.
A response from the previous topic could execute commands and overwrite the
new endpoint's cursor after commands were disabled or the server/topic changed.
The cursor write result was ignored, allowing a flash-write failure followed by
a reboot to replay a WOL command. Missing or oversized message IDs could bypass
replay protection; IDs containing query syntax could alter the next poll URL.

Settings were persisted through twelve independent key writes. A failure after
the first writes left partially changed settings on disk, although the web API
reported failure and the running worker retained the old configuration.

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
- A settings generation invalidates old in-flight poll responses after every
  successful save, including a disable/re-enable cycle or token/policy change.
  Each queued message is rechecked against the current policy before dispatch;
  a restored tunnel also stops queued commands under the offline-only policy.
  A command already accepted can finish; a disable is not cancellation of an
  already sent WOL packet or an already started network request.
- Configuration and endpoint-bound cursor are stored together in one versioned
  NVS blob (`ntfy_state_v1`), with serialized saves and explicit field validation.
  Failed saves do not publish partially changed live settings. Legacy settings
  migrate automatically; corrupt new records or migration errors leave ntfy
  disabled instead of silently falling back to an old enabled configuration.
- Message IDs must fit the cursor and contain only ASCII letters, digits, `-`
  or `_`. A missing/invalid ID cannot execute a command. The cursor must persist
  before dispatch; failure defers execution to a later successful poll.
- Password-protected encrypted backup/restore reads and writes the authoritative
  ntfy configuration, including the token. Normal status APIs remain redacted.
  Legacy NVS keys are retained for recovery but no longer updated: downgrading
  to older firmware can restore stale ntfy settings. Export an encrypted backup
  first and explicitly review/disable automation after a downgrade.

## Evidence and limitations

`tools/test_ntfy_transport.py` compiles the actual publish, poll, validation
and authorization functions with real cJSON and deterministic HTTP fixtures.
The pre-fix code failed the foreign-redirect regression; the corrected code
rejects 301/302/303/307/308, 401/403/500, header-allocation failure and invalid
tokens. Successful direct publishing/polling and anonymous topics still work.
The CI suite runs this fixture with address/undefined-behavior sanitizers.

The extended fixture calls the actual settings setter during a simulated HTTP
request and between messages, verifies disable/server/topic/token/policy changes,
checks missing/unsafe/oversized IDs, and injects NVS open/write/commit failures.
It reloads the actual saved configuration/cursor, tests legacy migration and
rejects corrupt records without falling back. It models NVS failures; it does
not emulate flash power cuts or prove long-term flash endurance.

The transport fixture does not implement real TLS or contact a live server.
Passing it does not prove that all firmware bugs or security issues are gone.
Hardware validation should include a direct HTTPS test notification, an info
command, WOL, migration/reboot, settings changes during command polling and a
self-hosted redirect refusal, using the exact candidate build. Very large
cached poll responses remain an open robustness item: the current bounded
buffer fails closed on overflow, but can stall replay until the backlog expires.
