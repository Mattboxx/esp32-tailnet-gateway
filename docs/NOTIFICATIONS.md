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
