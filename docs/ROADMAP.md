# Value/risk roadmap

> Historical strategy baseline. The newer user-approved full scope and release
> sequencing live in [DEVELOPMENT-ROADMAP.md](DEVELOPMENT-ROADMAP.md), with
> [FEATURE-IMPLEMENTATION-MATRIX.md](FEATURE-IMPLEMENTATION-MATRIX.md). Earlier
> selection/defer wording below does not remove requested temporary rules,
> sanitized export, Ethernet or other Master Prompt requirements.

This is a prioritized design, not a promise that every item will ship. Preserve
the packet path first. Existing controls remain unless an incompatibility is
demonstrated; no new dependency cloud or hardware is required.

## P0 — release gates and operational safety

1. **WoL durability/API correctness:** implemented in 1.14-dev.1; validate real
   NVS failure/reboot behavior before a stable release. No power-state claim.
2. **Tailnet policy boundary:** bounded local mitigation in 1.14-dev.2;
   complete [real-client/hardware qualification](TAILNET-AUTHORIZATION.md),
   required protocol/PMTU compatibility and independent review. No full
   official-client parity claim; unsupported policy must not become allow-all.
3. **Resource admission/isolation:** measure the simultaneous TLS/HTTP/MQTT/
   forwarding budget. Delay/refuse optional work under pressure with bounded
   backoff; preserve routing. No watchdog that reboots on broker/ntfy failures.
4. Keep pinned SDK/socket/partition/ntfy stack and existing routing fixtures;
   add physical roam/reconnect, all-services-down and restart-persistence runs.
5. Separate source candidate from published stable artifacts. Preserve
   license/credit notices and the exact tested-image packaging/hash checks.

## P1 — strong differentiation

1. **Selective service diagnostics/exposure:** first increment implemented.
   Explain installed versus tested, saved ingress/path/CIDR, unknown/stale
   state and corrective next steps without hidden traffic.
2. **Smart Recovery:** next substantial capability, behind resource and target-
   authorization gates. Saved target, precheck, explicitly requested one-shot
   WoL, bounded readiness follow-up, truthful result and optional notification.
   No forced power, remote shell or autonomous repeated wake loop.
3. **Layered health evidence:** passive first; optional named essential-service
   checks share the recovery worker instead of adding another permanent task.

## P2 — usability and interoperability

- Gateway/Recovery/IoT/Advanced as UI views first. Later presets require a
  before/after diff and explicit apply; never silently erase routes, rules,
  credentials or integration choices. One firmware, not four build flavors.
- Read-only capabilities manifest and commissioning templates selected below.
- A single operation/configuration registry for web/HA/ntfy over time, with
  preserved entity/topic identifiers and compatibility tests. No broad rewrite
  simply to reorganize menus into four product areas.
- Streamline duplicate README material, surface diagnostics where failures
  occur, and keep actionable unknown/disabled states visually distinct.

## P3 — defer or reject for now

- Ethernet: hardware-specific driver and actual uplink/route/NAPT support,
  not generic netif counters. Gate on a dedicated wired hardware test matrix.
- Temporary automatic rule expiry, active multi-peer monitoring and additional
  VPN protocols: no implementation before clock/lifecycle/resource designs.
- No KVM, electrical power control, shell execution or “universal HA bridge”.
  Those either need extra hardware or belong on a larger host.

## Evaluation of the six requested directions

| Direction | Value / decision | Feasibility, cost and risk |
|---|---|---|
| Smart Recovery | High differentiation; P1 next | Medium effort; one bounded async worker/socket, profile persistence and cancellation. Stack/heap not yet measured; cannot reserve more permanent internal RAM blindly. |
| Layered health monitor | High operational value; staged P1 | Passive part low cost; active probes need opt-in/backoff and a shared socket. Unknown route approval/Internet status must not become invented errors. |
| Selective service gateway | Highest existing differential; P1 completed increment | No new task/socket or data-path change here. Response size bounded by eight rules; real heap/latency still needs board measurement. |
| Profiles | Medium onboarding value; P2 views first | Low cost for views, medium/high risk for applying presets that affect remote access. Preserve explicit settings; require diff/confirmation. |
| Guided diagnostics | High support value; passive per-rule part implemented | Constant decision strings and existing snapshots; no service checks or ungrounded causes. Broader assistant waits for authoritative evidence. |
| Service isolation | Essential, not marketing; P0 | Extend current startup/backoff/ntfy bounds and one-shot MQTT outage WoL. Admission policy requires contention testing; avoid global restarts and duplicate recovery owners. |

## Five additional ideas, with resource assumptions

Scores: utility/differentiation/ESP32 feasibility 1–5 (higher is better).
Resource figures below are **design estimates, not measurements**. Flash means
additional firmware; stack/heap remain separate from static state. All features
would default disabled where they perform actions.

| Idea | Scores U/D/F | Complexity / estimated resources | Security / maintenance / reproducible test | Decision |
|---|---|---|---|---|
| Capability manifest: actual build/runtime drivers, supported policies and limits | 4/3/5 | Low; ~1–4 KB flash, ~1 KB transient JSON, no new stack/socket, negligible on-demand CPU | Low risk read-only; low maintenance if derived from code. Fixture with absent/present interfaces and exact build flags, then real boards. Prevents false Ethernet/universal-board claims. | **Select, P2** |
| Service commissioning templates: MQTT/SSH endpoints plus exposure preview | 4/3/5 | Low/medium; ~2–6 KB flash/UI strings, current rule storage, no new task/socket, negligible CPU | Medium misconfiguration risk; templates must start OFF and leave source/destination explicit. Low maintenance; browser/API snapshots and conflict tests. | **Select, P2** |
| Shared low-resource admission for optional TLS/probe/export jobs | 5/3/4 | Medium; ~2–8 KB flash, ~0.1–0.5 KB static bookkeeping, no extra socket/task solely for admission; sampling CPU low | Medium deadlock/starvation risk; never hold packet/lifecycle locks while waiting. Medium maintenance; allocation/socket fault injection and live worst-case contention. | **Select, P0** |
| Local sanitized support bundle, excluding credentials and topology by default | 4/2/4 | Medium; ~4–12 KB flash, bounded ~16–32 KB PSRAM transient or streamed, existing HTTP socket | Medium/high accidental disclosure risk; new redaction schema maintenance. Synthetic seeded secrets, nested JSON fuzz and no-network export tests. Existing diagnostics already cover much of the value. | Defer; improve existing local exports first |
| Time-limited forwarding grants with automatic expiry | 3/4/3 | Medium/high; ~4–12 KB flash, per-rule expiry metadata and clock/boot state; potentially no new task if existing manager owns it | High risk of unintended exposure or loss of remote access when time is wrong. Medium/high maintenance; clock rollback, unsynchronized boot, restart and in-flight rule replacement tests. | Defer, P3 |

Only the three selected additional ideas enter the active roadmap. Do not add
all five just because they are listed. The new passive exposure panel is a
foundation for commissioning, not proof that templates/manifest/admission
are already implemented.

## Sustainability and publish gate

- Keep protocol fixes upstream and maintain the smallest necessary custom
  microlink patch set, with exact pins and attribution. Review upstream changes
  by packet/lifecycle semantics, not release-number merges alone.
- Maintain one default supported binary target. Hardware variants need explicit
  driver ownership and evidence; price/power/throughput claims need measurements.
- Retain interface contracts for HA topics/entities, saved settings, web API,
  app name `esp32_tsr` and updater repository. Product naming is not migration.
- Before 1.14 publication: build/host/UI regressions, sanitizer run, exact-ELF
  stack review, live passive API/UI checks, WoL save/reload persistence, all
  optional integrations unavailable, heap/socket contention, no NVS changes to
  existing devices except explicitly requested saves, and private-data checks.
- No stable tag, firmware asset, remote flash or external announcement is
  created automatically by this development increment. Keep detailed test
  records local; user-facing release notes should focus on behavior and usage.
