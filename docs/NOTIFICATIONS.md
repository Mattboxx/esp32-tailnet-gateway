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

The unpublished 3.0.3-dev.1 candidate waits for **60 continuous seconds** before
queuing a Telegram or email warning about Wi-Fi or Tailnet connectivity.
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
