#pragma once

/* What the gateway does with the last Tailnet policy while the control plane
 * is unreachable (see ml_policy_set_control_loss). Names are the
 * /api/tailscale values; numbers are the ML_POLICY_LOSS_* values stored in
 * NVS as ts_loss_mode. Header-only so the host tests use the same code. */

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define CONTROL_LOSS_KEEP          0
#define CONTROL_LOSS_BOUNDED       1
#define CONTROL_LOSS_STRICT        2
#define CONTROL_LOSS_GRACE_MIN_S   30
#define CONTROL_LOSS_GRACE_MAX_S   86400
#define CONTROL_LOSS_GRACE_DEFAULT 300

/* -1 for an unknown name. */
static inline int control_loss_mode_parse(const char *name)
{
    if (!name) return -1;
    if (!strcmp(name, "keep")) return CONTROL_LOSS_KEEP;
    if (!strcmp(name, "bounded")) return CONTROL_LOSS_BOUNDED;
    if (!strcmp(name, "strict")) return CONTROL_LOSS_STRICT;
    return -1;
}

static inline const char *control_loss_mode_name(int32_t mode)
{
    return mode == CONTROL_LOSS_BOUNDED ? "bounded" : mode == CONTROL_LOSS_STRICT ? "strict" : "keep";
}

static inline bool control_loss_grace_valid(double seconds)
{
    return seconds >= CONTROL_LOSS_GRACE_MIN_S && seconds <= CONTROL_LOSS_GRACE_MAX_S
        && seconds == (double)(int32_t)seconds;
}
