/* Device-wide failed-login budget, on top of the per-client guard: cycling
 * source addresses must not reset online password guessing. Tradeoff: under
 * a sustained attack a legitimate operator also waits for a refill (at most
 * LOGIN_BUDGET_REFILL_US per attempt); nothing is persisted or locked out. */
#pragma once
#include <stdint.h>
#define LOGIN_BUDGET_BURST 10u
#define LOGIN_BUDGET_REFILL_US (3ULL * 1000000ULL)
typedef struct {uint32_t used; uint64_t since_us;} login_budget_t;

static inline void login_budget_refill(login_budget_t *b, uint64_t now)
{
    if (!b->used) return;
    if (now < b->since_us) {b->since_us = now; return;}
    uint64_t earned = (now - b->since_us) / LOGIN_BUDGET_REFILL_US;
    if (earned >= b->used) {b->used = 0; return;}
    b->used -= (uint32_t)earned;
    b->since_us += earned * LOGIN_BUDGET_REFILL_US;
}

/* Microseconds until one attempt is allowed; 0 = allowed now. */
static inline uint64_t login_budget_wait_us(login_budget_t *b, uint64_t now)
{
    login_budget_refill(b, now);
    return b->used < LOGIN_BUDGET_BURST ? 0 : b->since_us + LOGIN_BUDGET_REFILL_US - now;
}

static inline void login_budget_failed(login_budget_t *b, uint64_t now)
{
    login_budget_refill(b, now);
    if (!b->used) b->since_us = now;
    if (b->used < LOGIN_BUDGET_BURST) b->used++;
}
