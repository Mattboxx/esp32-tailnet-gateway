/* Restart optional integration workers (MQTT, ntfy) whose task could not be
 * created, e.g. under low memory at boot. Driven by the PSRAM operations
 * worker: no task, timer or internal-RAM cost of its own. Routing and the Web
 * UI never depend on it. Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {uint64_t next_ms; uint8_t failures; uint32_t restarts;} module_supervisor_t;

/* Delay after `failures` consecutive unsuccessful passes: 60 s doubling to 15 min. */
static inline uint32_t module_supervisor_delay_s(uint8_t failures)
{
    return failures >= 4 ? 900u : 60u << failures;
}

/* Returns true when this pass should try to (re)start missing workers. */
static inline bool module_supervisor_due(const module_supervisor_t *s, uint64_t now_ms, bool all_running)
{
    return !all_running && now_ms >= s->next_ms;
}

static inline void module_supervisor_result(module_supervisor_t *s, uint64_t now_ms, unsigned restarted, bool all_running)
{
    s->restarts += restarted;
    if (all_running) {s->failures = 0; s->next_ms = 0; return;}
    s->next_ms = now_ms + (uint64_t)module_supervisor_delay_s(s->failures) * 1000u;
    if (s->failures < UINT8_MAX) s->failures++;
}
