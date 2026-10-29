/* Opt-in power-return event, owned by the existing MQTT manager. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>

typedef struct {
    uint64_t retry_at_ms;
    uint32_t boot_id;
    uint8_t attempts;
    bool pending;
    bool power_on;
    bool selected_at_boot;
} mqtt_power_event_t;

static inline void mqtt_power_event_init(mqtt_power_event_t *s, uint32_t id,
                                         bool power_on, bool enabled, bool selected)
{
    *s = (mqtt_power_event_t){.boot_id = id ? id : 1, .power_on = power_on,
                              .pending = power_on && enabled && selected,
                              .selected_at_boot = power_on && enabled && selected};
}

static inline bool mqtt_power_event_due(mqtt_power_event_t *s, bool enabled,
                                        bool selected, bool connected,
                                        bool discovery_ready, uint64_t now_ms)
{
    /* Disabling cancels this boot's event. Enabling later never invents one.
     * Broker reconnects and configuration reloads do not rearm the event. */
    if (!enabled || !selected) {s->pending = false; s->selected_at_boot = false;}
    return s->pending && connected && discovery_ready && now_ms >= s->retry_at_ms;
}

static inline void mqtt_power_event_cancel(mqtt_power_event_t *s)
{s->pending = false; s->selected_at_boot = false;}

static inline void mqtt_power_event_result(mqtt_power_event_t *s, bool accepted,
                                           uint64_t now_ms)
{
    if (accepted || ++s->attempts >= 5) s->pending = false;
    else s->retry_at_ms = now_ms > UINT64_MAX - 30000 ? UINT64_MAX : now_ms + 30000;
}

static inline bool mqtt_power_event_json(char *out, size_t cap,
                                         const mqtt_power_event_t *s, uint64_t uptime_s)
{
    if (!out || !cap || !s || !s->pending || !s->power_on) return false;
    int n = snprintf(out, cap,
        "{\"event_type\":\"possible_blackout\",\"boot_id\":\"%08" PRIx32
        "\",\"reset_reason\":\"power_on\",\"uptime_s\":%" PRIu64 "}", s->boot_id, uptime_s);
    return n > 0 && (size_t)n < cap;
}
