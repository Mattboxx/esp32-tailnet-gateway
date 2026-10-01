# Automation UI loading fix

Version: `0.1.27-Mattboxx-1.6-dev.1` — October 1, 2026.

Opening or refreshing `#automation` previously sent protected API requests
before authentication had completed. After login, only Status was reloaded,
leaving Automation with its initial unchecked switches and dimmed cards.
MQTT rendering also depended on a second WOL fetch: a WOL network error
discarded a successful MQTT response.

Page requests now start after authentication, and login refreshes the selected
page. MQTT and ntfy load independently of WOL. Late WOL results refresh the
watchdog target names without replacing MQTT settings or discarding a saved
target. Repeated reloads share the same in-flight request.

Unknown configuration is displayed neutrally as Loading or Unavailable, never
as Disabled. Settings cannot be edited or saved until their first valid read.
Reads have an eight-second timeout and one retry for a transient failure.
Authentication failures and writes are not retried. Failed refreshes retain
the last loaded settings and explicitly identify them as stale; configuration
responses missing the boolean enabled field are rejected.

Validation: seven browser regression scenarios render the actual SPA with
synthetic APIs, including a real login-form submit with a mocked successful
authentication transport. ESP32-S3 compilation and static integration checks
are also run. Initial remote board verification was blocked by HTTP resets.
Local board validation on October 1 confirmed `dev.1`, five successful refreshes,
full-page reload, logout/login directly into Automation, and correct enabled
states for both integrations. MQTT publication was queued successfully and
the JavaScript console was clean. The ntfy test exposed a separate socket
allocation failure; see the [hardware validation](HARDWARE-1.6-VALIDATION.md).
