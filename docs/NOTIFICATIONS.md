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

`notify_cfg` (Telegram and email settings, CRC-checked; secrets never
returned by the API) and `ntf_mlv` (email event choice; absent = the shared
choice of 3.0.0). See [NVS keys](NVS-KEYS.md).
