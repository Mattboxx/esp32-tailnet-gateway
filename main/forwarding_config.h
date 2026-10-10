/* Serialize AP/Tailnet configuration transactions and joint install snapshots.
 * Lock order: this mutex, then either table's short state lock. Never queue a
 * TCP/IP callback while owning it: the callback also takes this mutex.
 * SPDX-License-Identifier: MIT */
#pragma once

void forwarding_config_lock(void);
void forwarding_config_unlock(void);
