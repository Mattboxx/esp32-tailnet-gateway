/* Opt-in ntfy system events, owned by the ntfy worker. One message per event,
 * bounded 60 s retry, nothing queued while disabled (no backlog flood when
 * enabled later). No allocation, socket or clock of its own. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

enum {NTFY_EVENT_BOOT = 1u, NTFY_EVENT_RESTORED = 2u, NTFY_EVENT_UPDATE = 4u};
typedef struct {uint8_t pending; uint16_t retry_s; uint32_t update_seen;} ntfy_events_t;

/* The legacy value 1 selected all system events, including power-on. */
static inline uint8_t ntfy_events_options(bool other, bool poweron)
{
    return other ? (poweron ? 1 : 3) : (poweron ? 2 : 0);
}
static inline void ntfy_events_decode(uint8_t value, bool *other, bool *poweron)
{
    *other = value == 1 || value == 3;
    *poweron = value == 1 || value == 2;
}

static inline void ntfy_events_init(ntfy_events_t *s) {*s = (ntfy_events_t){.pending = NTFY_EVENT_BOOT};}

/* Once per second. restored: an outage alert was delivered and Tailscale is
 * back. update_id: nonzero identity of an available, not-installed version. */
static inline void ntfy_events_tick(ntfy_events_t *s, bool enabled, bool restored, uint32_t update_id)
{
    if (!enabled) {s->pending = 0; s->retry_s = 0; if (update_id) s->update_seen = update_id; return;}
    if (restored) s->pending |= NTFY_EVENT_RESTORED;
    if (update_id && update_id != s->update_seen) {s->update_seen = update_id; s->pending |= NTFY_EVENT_UPDATE;}
    if (s->retry_s) s->retry_s--;
}

/* Drop disabled categories before checking the uplink. Enabling later never
 * invents a previous boot. Other events stay independent of power-on alerts. */
static inline void ntfy_events_select(ntfy_events_t *s, bool enabled, bool boot, bool other)
{
    uint8_t keep = enabled ? (boot ? NTFY_EVENT_BOOT : 0) |
        (other ? NTFY_EVENT_RESTORED | NTFY_EVENT_UPDATE : 0) : 0;
    s->pending &= keep;
    if (!s->pending) s->retry_s = 0;
}

/* Next event to send now, or 0. */
static inline unsigned ntfy_events_due(const ntfy_events_t *s)
{
    if (s->retry_s || !s->pending) return 0;
    for (unsigned bit = 1; bit <= NTFY_EVENT_UPDATE; bit <<= 1) if (s->pending & bit) return bit;
    return 0;
}

static inline void ntfy_events_result(ntfy_events_t *s, unsigned bit, bool delivered)
{
    if (delivered) s->pending &= (uint8_t)~bit;
    else s->retry_s = 60;
}
