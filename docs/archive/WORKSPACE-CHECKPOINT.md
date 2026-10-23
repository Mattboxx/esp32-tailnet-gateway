# Workspace continuation checkpoint — 2026-10-21

Development NOT complete. Current local source 0.1.38-Mattboxx-1.14-dev.5.
Root branch mattboxx, HEAD 8dbf06081392b292f37746a4858cf5a09f289757.
MicroLink HEAD 1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c.
Both worktrees remain dirty; no staging, commit, stash, reset, push, flash or
release. Essential policy/reassembly/health files are UNTRACKED and saved on
disk, not contained in those HEADs. Preserve the whole workspace and ignored
build/development-* artifacts/logs, plus unrelated COMMUNITY-POSTS.md.

Exact next task/evidence: NEXT-STEPS-FOR-AGENT.md and VALIDATION-STATUS.md.
Current image/ELF are in ignored build/development-0.1.38-Mattboxx-1.14-dev.5/current-source/.
Older candidates/intermediate snapshots remain intact. Stable board untouched.
All 42 roadmap items and the immutable Master Prompt remain applicable.

## Root inventory

```text
 M .github/workflows/sensitive-check.yml
 M CHANGELOG.md
 M CMakeLists.txt
 M CUSTOM_BRANCH.md
 M NOTICE.md
 M README.md
 M SECURITY.md
 M docs/releases/RELEASE-1.13.md
 M docs/TESTING.md
 m external/microlink
 M main/CMakeLists.txt
 M main/control_validation.h
 M main/index.html
 M main/main.c
 M main/mqtt_integration.c
 M main/ntfy_integration.c
 M main/ntfy_integration.h
 M main/tailnet_forward.c
 M main/tailnet_forward.h
 M main/web_ui.c
 M main/web_ui.h
 M main/wol.c
 M tools/package_release.py
 M tools/test_automation_ui.cjs
 M tools/test_control_validation.c
 M tools/test_forwarding_transactions.py
 M tools/test_ntfy_logic.py
 M tools/test_ntfy_transport.py
 M tools/test_tailnet_core.py
 M tools/test_tailnet_filter.py
 M tools/test_tailnet_sdk.py
 M tools/test_tailnet_state.py
?? AGENTS.md
?? GOALS.md
?? assets/logo/homelab-gateway.svg
?? docs/ARCHITECTURE-DECISIONS.md
?? docs/ARCHITECTURE.md
?? docs/COMMUNITY-POSTS.md
?? docs/DEVELOPMENT-ROADMAP.md
?? docs/FEATURE-IMPLEMENTATION-MATRIX.md
?? docs/MASTER-DEVELOPMENT-PROMPT.md
?? docs/NETWORK-HEALTH.md
?? docs/NEXT-STEPS-FOR-AGENT.md
?? docs/archive/PRODUCT-AUDIT.md
?? docs/releases/RELEASE-1.14-dev.1.md
?? docs/ROADMAP.md
?? docs/SERVICE-GATEWAY.md
?? docs/SMART-RECOVERY.md
?? docs/TAILNET-AUTHORIZATION.md
?? docs/VALIDATION-STATUS.md
?? docs/archive/WORKSPACE-CHECKPOINT.md
?? main/health_monitor.c
?? main/health_monitor.h
?? main/homelab_ops.c
?? main/homelab_ops.h
?? main/homelab_ops_http.c
?? main/service_diagnostics.h
?? main/service_lease.c
?? main/service_lease.h
?? main/web_origin.h
?? tools/observe_candidate.py
?? tools/probe_authorization.py
?? tools/test_candidate_observer.py
?? tools/test_development_plan.py
?? tools/test_gateway_operations.py
?? tools/test_health_monitor.py
?? tools/test_ops_api.py
?? tools/test_ops_core.py
?? tools/test_peer_convergence.py
?? tools/test_policy_protocols.py
?? tools/test_policy_reassembly.py
?? tools/test_service_lease.py
?? tools/test_tailnet_authorization.py
?? tools/validate_all.py
```

## Nested MicroLink inventory

```text
 M components/microlink/CMakeLists.txt
 M components/microlink/components/wireguard_lwip/src/wireguardif.c
 M components/microlink/src/ml_coord.c
 M components/microlink/src/ml_wg_mgr.c
?? components/microlink/include/ml_policy.h
?? components/microlink/include/ml_reassembly.h
?? components/microlink/src/ml_policy.c
?? components/microlink/src/ml_reassembly.c
```

