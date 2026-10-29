# Possible-blackout automations with Home Assistant

The 3.0.5 increment adds an optional power-return event to the existing MQTT
integration. It is independent of Telegram, email and ntfy settings.

## Enable

In **Automation → MQTT**, configure your broker, enable MQTT and
**Home Assistant MQTT discovery**, then enable
**Blackout: notify when power returns** and save. This option starts OFF.
Enable it before the next startup; saving settings never simulates a blackout.

Discovery adds to the gateway's existing Home Assistant device:

- **Possible blackout**: an MQTT event entity, event type `possible_blackout`.
- **Blackout: notify when power returns**: the corresponding switch.
- **Boot session**: an identifier that changes at ESP startup, not reconnection.
- **Last startup was power-on**: diagnostic information, not an ongoing outage.

In Home Assistant's automation editor, choose **Event received**, select the
gateway's **Possible blackout** entity and its `possible_blackout` event type.
Choose your notification, scene or other desired action. Older versions can
use an MQTT trigger on the event topic below.

Only a hardware power-on reset qualifies. Software restarts, firmware updates,
panic/watchdog resets, deep-sleep wakeups and short Wi-Fi/MQTT disconnections
do not generate this event. First power-up or reconnecting a USB cable can
produce the same power-on reset: this is **a possible blackout, not proof of
a utility outage or its duration**. Nothing can be sent while unpowered.

## Topics and delivery

Replace `BASE` with the configured MQTT base topic.

| Topic | Purpose |
| --- | --- |
| `BASE/event/power` | Non-retained QoS 1 event, eligible only once per boot |
| `BASE/state` | Existing retained state, now includes boot diagnostics |
| `BASE/command/poweron_events` | Existing authenticated-broker command path; `ON` or `OFF` |

Example event:

```json
{"event_type":"possible_blackout","boot_id":"1234abcd","reset_reason":"power_on","uptime_s":72}
```

The event waits for the broker and, when enabled, the paced discovery pass.
Failed local publish attempts retry at most five times with a 30-second margin.
Once the MQTT client accepts the event, the firmware does not generate another
on reconnect or ordinary state refresh. QoS 1 itself can redeliver a packet:
use `boot_id` to deduplicate consequential automations. Acceptance is not an
acknowledgment that Home Assistant executed an automation.

Turning MQTT or this option off, or saving MQTT settings, cancels an unsent
startup event. Turning them back on during the same boot does not create one.
Broker outages/reconnects alone do not cancel an eligible event or rearm a
completed event. `uptime_s` reveals a delayed notification.

## If Home Assistant starts later

Event messages are intentionally not retained. Home Assistant may miss a live
event while offline; its MQTT event platform discards replayed retained events.
The existing retained `BASE/state` carries:

- `boot_id`: stable during this ESP boot, including broker reconnects.
- `power_on_boot`: `ON` only for a hardware power-on reset.
- `poweron_events`: the saved switch state.
- `poweron_event_boot`: `ON` if this startup was eligible for the event; a
  settings edit/disable cancels eligibility as described above.

An automation can reconcile this state when HA returns. Keep the last processed
boot id in a persistent Text helper; do not set an `initial` value that erases
it at each HA restart. This avoids notifications merely because HA/MQTT reloads.

The following example uses both live events and retained-state catch-up.
Create a Text helper `input_text.gateway_last_power_boot` (at least 8 characters),
replace both example topics, and paste the automation in HA's YAML editor:

```yaml
alias: Gateway possible blackout
mode: queued
max: 4
triggers:
  - trigger: mqtt
    topic: esp32-router/EXAMPLE/event/power
    id: live
  - trigger: mqtt
    topic: esp32-router/EXAMPLE/state
    id: catch_up
conditions:
  - condition: template
    value_template: >-
      {% set p = trigger.payload_json | default({}) %}
      {{ p.get('boot_id', '') | length == 8
         and p.get('boot_id') != states('input_text.gateway_last_power_boot')
         and ((trigger.id == 'live' and p.get('event_type') == 'possible_blackout')
              or (trigger.id == 'catch_up' and p.get('poweron_event_boot') == 'ON'
                  and p.get('poweron_events') == 'ON')) }}
actions:
  # Queued triggers can pass the outer condition before an earlier run stores
  # the id. Recheck it when this queued run actually starts executing.
  - condition: template
    value_template: >-
      {{ trigger.payload_json.boot_id != states('input_text.gateway_last_power_boot') }}
  - action: input_text.set_value
    target:
      entity_id: input_text.gateway_last_power_boot
    data:
      value: "{{ trigger.payload_json.boot_id }}"
  - action: persistent_notification.create
    data:
      notification_id: gateway_possible_blackout
      title: Possible blackout
      message: >-
        The ESP gateway powered on. This can mean power returned,
        first startup or a reconnected cable. Check your equipment.
```

Use one helper per gateway. The example records a boot id before notifying;
it is a practical duplicate guard, not a transactional or exactly-once alarm
system. Check HA's automation traces after configuring it.

## Maintainer/resource notes

There is no new task, socket, timer callback, persistent queue or enlarged log
buffer. Config size stays 496 bytes; `poweron_events` occupies existing padding.
The manager's existing PSRAM stack holds a 16-byte event state. Event formatting
is bounded to 160 bytes, uses the existing QoS 1 outbox and does not retain its
payload. The optional `mqtt_pwr` NVS byte defaults to OFF; old firmware ignores
it. State stays within the existing 6144-byte budget through existing compaction.

Reference: [Home Assistant MQTT Event](https://www.home-assistant.io/integrations/event.mqtt/),
[event automations](https://www.home-assistant.io/integrations/event/) and
[MQTT triggers](https://www.home-assistant.io/docs/automation/trigger/#mqtt-trigger).
Physical power-cycle, broker and real Home Assistant results are separate
from host fixtures; detailed execution evidence belongs in the private handover.
