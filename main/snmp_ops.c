/* SNMP opt-in agent pulls a bounded, numeric snapshot; no new task or socket. MIT. */
#include "snmp_ops.h"
#include "snmp_operational.h"
#include "homelab_ops.h"
#include "ml_policy.h"
#include "tailnet_forward.h"
#include "mqtt_integration.h"
#include "tailscale_config.h"
#include "service_evidence.h"
#include "service_lease.h"
#include "esp_system.h"
#include <string.h>
static void operational_metrics(snmp_operational_metrics_t *out) {
    memset(out,0,sizeof *out);
    ops_resources_t r;homelab_ops_resources(&r);
    ml_policy_status_t p;ml_policy_get_status(&p);
    uint32_t enabled=0,installed=0,accepted=0,blocked=0;
    tailnet_forward_totals(&enabled,&installed,&accepted,&blocked);
    out->value[SNMP_OPS_AVAILABLE]=1;
    out->value[SNMP_OPS_INTERNAL_FREE]=r.internal_free;
    out->value[SNMP_OPS_INTERNAL_MIN]=r.internal_min;
    out->value[SNMP_OPS_INTERNAL_LARGEST]=r.internal_largest;
    out->value[SNMP_OPS_PSRAM_FREE]=r.psram_free;
    out->value[SNMP_OPS_PSRAM_MIN]=r.psram_min;
    out->value[SNMP_OPS_PSRAM_LARGEST]=r.psram_largest;
    out->value[SNMP_OPS_SOCKETS_USED]=r.sockets_used;
    out->value[SNMP_OPS_SOCKET_LIMIT]=r.socket_limit;
    out->value[SNMP_OPS_WORKER_RUNNING]=r.worker_running;
    out->value[SNMP_OPS_WORKER_STACK_RAW]=r.worker_running?r.worker_stack_min:UINT32_MAX;
    out->value[SNMP_OPS_AUTHORITY_READY]=p.authority_ready;
    out->value[SNMP_OPS_POLICY_PEERS]=p.peers;
    out->value[SNMP_OPS_RETURN_FLOWS]=p.return_flows;
    out->value[SNMP_OPS_FORWARD_ENABLED]=enabled;
    out->value[SNMP_OPS_FORWARD_INSTALLED]=installed;
    out->value[SNMP_OPS_FORWARD_ACCEPTED]=accepted;
    out->value[SNMP_OPS_FORWARD_BLOCKED]=blocked;
    out->value[SNMP_OPS_MQTT_CONNECTED]=mqtt_integration_connected();
    out->value[SNMP_OPS_CONTROL_CONNECTED]=tailscale_is_connected();
    out->value[SNMP_OPS_RESET_REASON]=esp_reset_reason();
    for(int i=0;i<TAILNET_FORWARD_MAX;i++){
        tailnet_forward_rule_t rule;tailnet_forward_runtime_t rt;if(!tailnet_forward_get(i,&rule,&rt))continue;
        service_evidence_t ev;service_evidence_collect(i,service_lease_token(&rule),&rule,&rt,true,true,&ev);
        if(ev.checked&&ev.check.state==SC_REACHABLE)out->value[SNMP_OPS_FORWARD_REACHABLE]++;
        if(ev.replied)out->value[SNMP_OPS_FORWARD_REPLIED]++;
    }
}
void homelab_snmp_register(void){snmp_agent_set_operational_provider(operational_metrics);}
