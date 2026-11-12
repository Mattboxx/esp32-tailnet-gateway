# Licence of the Mattboxx Edition, additional permission and terms

ESP32 Tailnet Gateway — Mattboxx Edition
Copyright (C) 2026 Mattboxx

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License version 3 as published by the Free
Software Foundation (SPDX: `GPL-3.0-only`), with the additional permission and
the additional terms below. The full licence text is in [LICENSE](LICENSE).

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

## Scope

- From 8 November 2026 the Mattboxx Edition is distributed only under this
  licence. This covers all code written for the Mattboxx Edition, including
  code that first appeared in earlier releases, in the current source and in
  every release from **3.0.12** on. Its author no longer offers that code
  under any other licence.
- Releases up to and including 3.0.11 were distributed under the MIT License,
  and the historical revisions in this repository still carry that notice. A
  licence already granted cannot be withdrawn: copies of those releases and
  revisions keep the MIT terms they were published with. Nothing here claims
  otherwise; it only applies to what is distributed from now on.
- Code from the original firmware by Csontikka stays available under its MIT
  License, kept verbatim in
  [licenses/upstream/esp32-tailscale-subnet-router-MIT.txt](licenses/upstream/esp32-tailscale-subnet-router-MIT.txt).
  The pinned MicroLink fork (`external/microlink`) has its own GPLv3 linking
  permission and preserves the original MicroLink MIT notice. Earlier
  releases retain the terms of the revision they included. Other third-party
  components keep their own terms (see [NOTICE.md](NOTICE.md)).
  Those notices must be preserved in every copy.

## Additional permission (GNU GPL version 3, section 7)

If you modify this Program, or any covered work, by linking or combining it
with the ESP-IDF framework or with the binary-only libraries that Espressif
Systems distributes with ESP-IDF and its components (for example the Wi-Fi,
Bluetooth, PHY and coexistence libraries and the ROM code), or modified
versions of those libraries, containing parts covered by the terms of their
own licences, the licensors of this Program grant you additional permission to
convey the resulting work. Corresponding Source for a non-source form of such
a combination shall include the source code for the parts of ESP-IDF used as
well as that of the covered work, but need not include source code of those
binary-only libraries that Espressif does not publish as source.

## Additional terms (GNU GPL version 3, section 7(b), 7(c) and 7(e))

- **Attribution (7(b)).** Keep the author attributions in
  [NOTICE.md](NOTICE.md) and in the firmware's About page (System > About) in
  conveyed copies, including the original authors named there.
- **Marking of modified versions (7(c)).** A modified version must be marked
  in reasonable ways as different from the original: it must not be presented
  as the official Mattboxx Edition or as a release of this project, and it must
  carry a prominent notice that it was changed.
- **Names and marks (7(e)).** This licence does not grant rights under
  trademark law to use the names "Mattboxx" or "Mattboxx Edition", or the
  Mattboxx artwork in `assets/brand/`, as names or marks of other products or
  services, except for reasonable and customary use in describing the origin
  of the work and in reproducing the notices above.

These terms add no restriction beyond those section 7 of the GNU GPL version 3
permits. Tailscale, Headscale, WireGuard, Espressif and ESP32 are names of
their respective owners and are not licensed here.
