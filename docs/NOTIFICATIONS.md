# Telegram and email notifications

Automation → **Notifications** has three independent cards: ntfy
([NTFY.md](NTFY.md)), **Telegram** and **Email**. Each is off by default; while
both Telegram and email are off nothing runs. A delivery worker exists only
while a message waits.

## What is sent

Starts, crashes, updates, uplink and tailnet changes, failed admin logins,
settings copies and dynamic DNS results (from the event history bus), plus
the operational results ntfy also sends (recovery checks, service rules).
Each channel has its own **Send** choice: *Warnings and errors* (recommended)
or *All events*. Operational results are always sent. At most 6 messages at
once, then one every two minutes, so an outage storm stays short.

## Telegram

1. Create a bot with **@BotFather** and copy its token.
2. Send the bot any message; get your chat id (for example from
   **@userinfobot**). Groups start with `-`, channels can use `@name`.
3. Enter token and chat id, turn on *Send to Telegram*, Save, then *Send
   test*. The card shows sent/failed counts and the last error.

Messages go through Telegram's servers. The token is write-only.

## Email

SMTP server, connection (**TLS from the start**, port 465, or **STARTTLS**,
port 587), user name and password, From and To.

- The server certificate is always verified against the built-in bundle; the
  password is never sent before TLS is up.
- Many providers need an **app password** (Gmail, Outlook, iCloud with
  two-factor authentication).
- Errors say what to do first, then show the server's own words, for example
  *sign-in required: enter the user name and password* or *user name or
  password not accepted (many providers need an app password)*.

Tested on a board: TLS (465) and STARTTLS (587) to a real provider up to the
sign-in step, and refusal of wrong-name and self-signed certificates.
Delivery through a real account is up to you to confirm with *Send test*.

## Storage

One CRC-checked record, `notify_cfg`, holds the Telegram and email settings
and the email event choice, so a save is all or nothing; secrets are never
returned by the API. 3.0.1 kept the email choice in a second key, `ntf_mlv`:
a failed second write could leave the record changed although the page
reported an error. From the next release the record decides; `ntf_mlv` is
still written after it, only so that a rollback to 3.0.1 keeps the choice, and
3.0.0/3.0.1 records migrate. See [NVS keys](NVS-KEYS.md).
# Candidate change: brief connectivity interruptions

The unpublished 3.0.3-dev.1 candidate waits for **60 continuous seconds by default** before
queuing a Telegram or email warning about Wi-Fi or Tailnet connectivity.
The common **Connectivity alerts** timer accepts 15–3600 whole seconds, saved
independently of the channel credentials. ntfy retains its own failure delay.
Short drops and their corresponding recoveries do not create a delayed
notification. Local event history remains controlled by its existing enable
switch and rate/queue limits. Wi-Fi and Tailnet have independent windows;
other uplink events such as DDNS errors cannot reset them. Other warning/error
types, security/crash events and explicit tests retain their existing policy.

Only one pending warning is created for an ongoing incident. If connectivity
returns while it is queued, its text becomes a duration-based recovery summary.
If transport retries expired during a long outage, an undelivered channel can
receive the summary after recovery. A request already accepted by an external
server cannot be recalled; network acknowledgement loss can still produce
duplicates during retries. This is not an exactly-once delivery guarantee.

The existing history task performs the bounded poll: no new task, timer, socket
or NVS record is added for the grace period. The queue/state costs a small
additional PSRAM/static allocation; compiled sizes are recorded privately,
and runtime heap/stack impact still needs actual candidate hardware testing.
When task creation fails, the existing queue is retried after 30 seconds with
exponential backoff capped at five minutes. Persisted settings and channel
selections retain the 3.0.2 schema and rollback format.

The Automation Refresh button updates Telegram/email delivery status too.
Status polls preserve drafts and independently saved cards, and an older
response cannot replace a newer one. The token/password remains write-only.

## Candidate change: power-on and other restarts

Telegram, email and ntfy each have **Blackout: notify when power returns**.
This selects a hardware POWERON reset, independently of other restarts.
Telegram/email also have **Other restarts**, independently of **Warnings and
errors** / **All events**. The choices apply to the next boot and do not enable
the channel itself. Neither startup category waits for the connectivity timer;
delivery still needs the network. Telegram/email crash, watchdog and brownout
errors retain their existing warning/error path even when both startup switches
are off. A brownout is identified separately as a voltage drop, not a full outage.

ntfy's **Other restarts, Tailscale restored after an alert, update available**
selection remains separate from its power-on switch. Its startup message
distinguishes power-on, software restart, supply voltage drop and fault reset;
power-on alone cannot trigger a crash message. Enabling a category after boot
does not replay that old startup. Existing retries and channel limits still
apply; no transport guarantees exactly-once delivery.

A powered-off ESP cannot notify during the cut. A POWERON reset indicates
that power/reset was applied, not proof of a utility outage or its duration.
These switches report the board starting; they do not measure mains supply.

The Telegram/email choices occupy the last padding byte of the same
CRC-checked `notify_cfg` record, with a presence marker and four selection bits
(two channels for other starts, two for power-on).
No configuration struct size, NVS key, record version or checksum range changes.
An old record preserves its previous behavior (startup selected for that
channel's All-events mode); fresh/invalid settings stay off. Explicit choices
are saved atomically with the rest of the card, and omitted fields preserve
them. Old firmware accepts the record on rollback but uses its own older
event-selection behavior. Unknown flag bits fail closed.

ntfy keeps its existing main record unchanged. Its separate `ntfy_sysev` byte
is 0=neither category, 1=both (legacy enabled), 2=power-on only, 3=other system
events only. Invalid values disable both categories. On rollback, older
firmware interprets 2/3 as its optional System-events switch off; users can
reselect the legacy option there. Endpoints, secrets and replay cursors are
unchanged. Failed saves do not publish new choices in RAM.

The Telegram field is labelled **Destination user id** with an expandable
guide. The Telegram API still calls the transport value `chat_id`; group ids
and channel destinations remain supported. No helper bot or Telegram API is
contacted by merely opening the guide.

## Candidate change: local error context

At the owner's request, live log, RTC and Web log read-buffer allocation
remain unchanged: **16 KiB live** and **4 KiB RTC**, with the existing fallback.
The proposed 64 KiB expansion was withdrawn before any build/install/publication.
No additional diagnostic buffer, queue or task is introduced.
Failure diagnostics record channel, event/message id,
attempt, error code, free internal memory, largest block and free PSRAM,
without message bodies, bot tokens, passwords or destination ids.

Live logs are volatile; a cold
power cut does not preserve them. This adds no automatic uploads or flash
writes per log line. CPU/heap/stack behavior on real hardware still needs
candidate qualification; host tests do not measure those runtime budgets.
