/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Validate the entire request before allocating a lease. Ethernet DHCPv4
 * requests are bounded to one standard MTU, including reassembled pbufs. */
#define DHCPS_MAX_REQUEST_LEN 1500
static inline bool dhcps_request_valid(const uint8_t *data, size_t length)
{
    if (!data || length < 244 || length > DHCPS_MAX_REQUEST_LEN) return false;
    if (data[0] != 1 || data[1] != 1 || data[2] != 6) return false;
    if (data[236] != 99 || data[237] != 130 || data[238] != 83 || data[239] != 99)
        return false;
    bool have_type = false;
    size_t offset = 240;
    while (offset < length) {
        uint8_t option = data[offset++];
        if (option == 0) continue;
        if (option == 255) return have_type;
        if (offset == length) return false;
        size_t size = data[offset++];
        if (size > length - offset) return false;
        if (option == 53) {
            if (have_type || size != 1) return false;
            uint8_t type = data[offset];
            if (type != 1 && type != 3 && type != 4 && type != 7) return false;
            have_type = true;
        } else if (option == 50 && size != 4) {
            return false;
        }
        offset += size;
    }
    return false;
}
