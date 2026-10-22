#pragma once
#include <stdbool.h>
#include <stdint.h>

/* One worker owns this state. No allocation, socket, task or wall-clock use. */
typedef struct {
    uint64_t next_ms;
    uint8_t failures;
    bool awaiting;
} service_retry_t;

static inline void service_retry_reset(service_retry_t *r)
{
    *r = (service_retry_t){0};
}

static inline bool service_retry_due(const service_retry_t *r, uint64_t now)
{
    return !r->awaiting && now >= r->next_ms;
}

static inline void service_retry_begin(service_retry_t *r, uint64_t now)
{
    r->awaiting = true;
    r->next_ms = now + 30000;
}

static inline bool service_retry_timed_out(const service_retry_t *r, uint64_t now)
{
    return r->awaiting && now >= r->next_ms;
}

static inline void service_retry_failed(service_retry_t *r, uint64_t now)
{
    uint32_t delay = r->failures < 6 ? 5000u << r->failures : 300000u;
    if (r->failures < 7) r->failures++;
    r->awaiting = false;
    r->next_ms = now + delay;
}
