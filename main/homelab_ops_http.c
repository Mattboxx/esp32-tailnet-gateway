/* Authenticated operational APIs. No arbitrary URL, shell or power controls. */
#include "homelab_ops.h"
#include "service_lease.h"
#include "health_monitor.h"
#include "json_guard.h"
#include "service_transfer.h"
#include "config_profiles.h"
#include "service_check.h"
#include "eth_uplink.h"
#include "cell_uplink.h"
#include "layout_migration.h"
#include "history.h"
#include "settings_snapshot.h"
#include "service_evidence.h"
#include "ml_policy.h"
#include "esp_timer.h"
#include "portmap.h"
#include "sdkconfig.h"
#include "web_ui.h"
#include "esp_heap_caps.h"
#include "esp_app_desc.h"
#include "esp_system.h"
#include "mqtt_integration.h"
#include "ntfy_integration.h"
#include "snmp_agent.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

static bool integer(const cJSON *root,const char *name,unsigned maximum,unsigned *out) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(root,name);
    if(!cJSON_IsNumber(v) || !isfinite(v->valuedouble) || v->valuedouble<0 || v->valuedouble>maximum || floor(v->valuedouble)!=v->valuedouble)return false;
    *out=(unsigned)v->valuedouble;return true;
}
static bool boolean(const cJSON *root,const char *name,uint8_t *out) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(root,name);if(!cJSON_IsBool(v))return false;*out=cJSON_IsTrue(v);return true;
}
static bool unique(const cJSON *o) {
    if(!cJSON_IsObject(o))return false;
    for(const cJSON *a=o->child;a;a=a->next)for(const cJSON *b=a->next;b;b=b->next)
        if(!a->string || !b->string || !strcmp(a->string,b->string))return false;
    return true;
}
static esp_err_t send_json(httpd_req_t *req,cJSON *root) {
    if(!root){httpd_resp_send_500(req);return ESP_FAIL;}
    char *body=cJSON_PrintUnformatted(root);cJSON_Delete(root);if(!body){httpd_resp_send_500(req);return ESP_FAIL;}
    httpd_resp_set_type(req,"application/json");httpd_resp_set_hdr(req,"Cache-Control","no-store");
    esp_err_t err=httpd_resp_sendstr(req,body);free(body);return err;
}
static esp_err_t get_ops(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    return send_json(req,homelab_ops_snapshot(true));
}
static esp_err_t get_capabilities(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    return send_json(req,homelab_ops_capabilities());
}
static esp_err_t get_leases(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    return send_json(req,service_lease_snapshot());
}
static esp_err_t get_health(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    return send_json(req,health_monitor_snapshot(true));
}
/* Service Gateway evidence without names, destinations, ports or source
 * networks: state, diagnosis codes, test state, counters and ages only. */
static bool export_service_rules(cJSON *root) {
    cJSON *rules=cJSON_AddArrayToObject(root,"service_gateway_rules");if(!rules)return false;
    uint32_t now_s=(uint32_t)(esp_timer_get_time()/1000000)+1u;
    for(int i=0;i<TAILNET_FORWARD_MAX;i++){
        tailnet_forward_rule_t r;tailnet_forward_runtime_t rt;if(!tailnet_forward_get(i,&r,&rt))continue;
        /* Uplink/control are reported elsewhere in the export; treat them as up
         * here so the code describes the rule, not a global fault. */
        service_evidence_t ev;service_evidence_collect(i,service_lease_token(&r),&r,&rt,true,true,&ev);
        service_diagnostic_t d=ev.diag;service_check_result_t check=ev.check;bool checked=ev.checked,replied=ev.replied;uint32_t reply_ms=ev.reply_ms;
        cJSON *item=cJSON_CreateObject();
        if(!item||!cJSON_AddItemToArray(rules,item)){cJSON_Delete(item);return false;}
        if(!cJSON_AddNumberToObject(item,"index",i)||!cJSON_AddStringToObject(item,"protocol",r.proto==TAILNET_FORWARD_PROTO_UDP?"udp":"tcp")
            ||!cJSON_AddBoolToObject(item,"enabled",r.enabled)||!cJSON_AddBoolToObject(item,"installed",rt.installed)
            ||!cJSON_AddBoolToObject(item,"single_source",r.source_prefix==32)||!cJSON_AddBoolToObject(item,"runtime_error",rt.error[0]!=0)
            ||!cJSON_AddStringToObject(item,"diagnostic",d.code)
            ||!cJSON_AddStringToObject(item,"destination_check",service_check_state_name(checked?check.state:SC_NONE))
            ||!cJSON_AddNumberToObject(item,"accepted_packets",rt.accepted_packets)||!cJSON_AddNumberToObject(item,"rejected_packets",rt.blocked_packets)
            ||!(rt.last_accepted_s?cJSON_AddNumberToObject(item,"last_accepted_age_s",now_s>=rt.last_accepted_s?now_s-rt.last_accepted_s:0):cJSON_AddNullToObject(item,"last_accepted_age_s"))
            ||!(replied?cJSON_AddNumberToObject(item,"service_reply_age_s",reply_ms/1000):cJSON_AddNullToObject(item,"service_reply_age_s")))return false;
    }
    return true;
}
/* Module and configuration summary: states and counts only, no addresses,
 * names, URLs, topics or credentials. */
static bool export_system_summary(cJSON *root) {
    cJSON *s=cJSON_AddObjectToObject(root,"system_summary");if(!s)return false;
    ntfy_integration_status_t ntfy;ntfy_integration_get_status(&ntfy);ntfy_integration_config_t nc;ntfy_integration_get_config(&nc);
    mqtt_integration_status_t mqtt;mqtt_integration_get_status(&mqtt);
    eth_status_t eth;eth_uplink_get_status(&eth);
    service_watch_config_t watch;service_watch_get(&watch);
    profile_id_t profile;bool rollback;config_profiles_status(&profile,&rollback);
    return cJSON_AddNumberToObject(s,"uptime_s",(double)(esp_timer_get_time()/1000000))
        &&cJSON_AddNumberToObject(s,"internal_heap_minimum",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL))
        &&cJSON_AddBoolToObject(s,"mqtt_task_running",mqtt_integration_task_running())
        &&cJSON_AddBoolToObject(s,"mqtt_configured",mqtt.configured)
        &&cJSON_AddBoolToObject(s,"ntfy_task_running",ntfy.task_running)
        &&cJSON_AddBoolToObject(s,"ntfy_enabled",nc.enabled)&&cJSON_AddBoolToObject(s,"ntfy_commands",nc.commands_enabled)
        &&cJSON_AddBoolToObject(s,"ntfy_system_events",nc.system_events)
        &&cJSON_AddBoolToObject(s,"ethernet_compiled",eth.compiled)&&cJSON_AddBoolToObject(s,"ethernet_enabled",eth.enabled_at_boot)
        &&cJSON_AddBoolToObject(s,"ethernet_driver_started",eth.driver_started)&&cJSON_AddBoolToObject(s,"ethernet_link_up",eth.link_up)
        &&cJSON_AddBoolToObject(s,"ethernet_selected_uplink",eth.selected)&&cJSON_AddBoolToObject(s,"ethernet_error",eth.error[0]!=0)
        &&cJSON_AddBoolToObject(s,"service_watch_enabled",watch.enabled)&&cJSON_AddNumberToObject(s,"service_watch_interval_s",watch.interval_s)
        &&cJSON_AddStringToObject(s,"profile",config_profile_name(profile))&&cJSON_AddBoolToObject(s,"profile_rollback_available",rollback);
}
static esp_err_t get_export(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    cJSON *root=homelab_ops_snapshot(false);if(!root){httpd_resp_send_500(req);return ESP_FAIL;}
    cJSON_AddNumberToObject(root,"schema",1);cJSON_AddStringToObject(root,"scope","sanitized-operational-subset");
    const esp_app_desc_t *app=esp_app_get_description();cJSON_AddStringToObject(root,"version",app?app->version:"unknown");
    cJSON_AddNumberToObject(root,"reset_reason_code",esp_reset_reason());
    cJSON_AddNumberToObject(root,"task_count",uxTaskGetNumberOfTasks());
    cJSON_AddNumberToObject(root,"mqtt_watchdog_wakes",mqtt_integration_watchdog_wake_count());
    cJSON_AddBoolToObject(root,"mqtt_connected",mqtt_integration_connected());
    mqtt_integration_status_t mqtt;mqtt_integration_get_status(&mqtt);
    cJSON_AddBoolToObject(root,"mqtt_configured",mqtt.configured);cJSON_AddNumberToObject(root,"mqtt_retry_level",mqtt.retry_level);
    cJSON_AddNumberToObject(root,"mqtt_retry_in_seconds",mqtt.retry_in_seconds);cJSON_AddBoolToObject(root,"mqtt_discovery_pending",mqtt.discovery_pending);
    ntfy_integration_status_t ntfy;ntfy_integration_get_status(&ntfy);
    cJSON_AddNumberToObject(root,"ntfy_alerts_sent",ntfy.alerts_sent);cJSON_AddNumberToObject(root,"ntfy_command_errors",ntfy.command_errors);
    cJSON_AddBoolToObject(root,"snmp_enabled",snmp_agent_is_enabled());cJSON_AddBoolToObject(root,"snmp_running",snmp_agent_is_running());
    uint32_t enabled=0,installed=0,accepted=0,blocked=0;tailnet_forward_totals(&enabled,&installed,&accepted,&blocked);
    cJSON_AddNumberToObject(root,"forwarding_enabled",enabled);cJSON_AddNumberToObject(root,"forwarding_installed",installed);
    cJSON_AddNumberToObject(root,"forwarding_accepted_packets",accepted);cJSON_AddNumberToObject(root,"forwarding_blocked_packets",blocked);
    if(!export_service_rules(root)||!export_system_summary(root)){cJSON_Delete(root);httpd_resp_send_500(req);return ESP_FAIL;}
    cJSON *capabilities=homelab_ops_capabilities();
    if(!capabilities || !cJSON_AddItemToObject(root,"capabilities",capabilities)){
        cJSON_Delete(capabilities);cJSON_Delete(root);httpd_resp_send_500(req);return ESP_FAIL;
    }
    httpd_resp_set_hdr(req,"Content-Disposition","attachment; filename=homelab-diagnostics.json");return send_json(req,root);
}
static esp_err_t post_ops(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    if(req->content_len<2 || req->content_len>1536){httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid body size");return ESP_FAIL;}
    char *body=heap_caps_calloc(1,(size_t)req->content_len+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!body){httpd_resp_send_500(req);return ESP_FAIL;}
    int n=0;while(n<req->content_len){int got=httpd_req_recv(req,body+n,req->content_len-n);if(got<=0){free(body);httpd_resp_send_408(req);return ESP_FAIL;}n+=got;}
    cJSON *root=json_guard_preflight(body,(size_t)n)?json_guard_parse(body):NULL;free(body);
    if(!root || !unique(root)){cJSON_Delete(root);httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid JSON object");return ESP_FAIL;}
    const cJSON *action=cJSON_GetObjectItemCaseSensitive(root,"action");esp_err_t err=ESP_ERR_INVALID_ARG;unsigned index;
    if(cJSON_IsString(action)){
        if(!strcmp(action->valuestring,"cancel"))err=homelab_ops_cancel();
        else if(!strcmp(action->valuestring,"lease")){
            unsigned seconds,token;uint8_t permanent,remove=0;
            if(integer(root,"index",TAILNET_FORWARD_MAX-1,&index)&&integer(root,"rule_token",UINT32_MAX,&token)
                && integer(root,"seconds",604800,&seconds)&&boolean(root,"permanent",&permanent)
                && (!cJSON_GetObjectItemCaseSensitive(root,"delete_on_expiry")||boolean(root,"delete_on_expiry",&remove))){
                err=service_lease_set_mode(index,token,seconds,permanent,remove);
                if(err==ESP_OK)portmap_install_all();
            }
        }
        else if(!strcmp(action->valuestring,"settings")){
            ops_settings_t s={0};unsigned interval,minimum,largest,reserve;
            if(boolean(root,"monitoring",&s.monitoring)&&boolean(root,"guard",&s.guard)&&boolean(root,"remote_commands",&s.remote_commands)
                && (!cJSON_GetObjectItemCaseSensitive(root,"lease_notifications")||boolean(root,"lease_notifications",&s.lease_notifications))
                && integer(root,"interval_s",3600,&interval)&&integer(root,"minimum_internal",262144,&minimum)
                && integer(root,"minimum_largest",131072,&largest)&&integer(root,"socket_reserve",CONFIG_LWIP_MAX_SOCKETS,&reserve)){
                s.interval_s=interval;s.minimum_internal=minimum;s.minimum_largest=largest;s.socket_reserve=reserve;err=homelab_ops_set_settings(&s);
            }
        }else if(!strcmp(action->valuestring,"health")){
            health_config_t c={0};unsigned interval,threshold,gateway,internet,tailnet;
            const cJSON *dns=cJSON_GetObjectItemCaseSensitive(root,"dns_name"),*ip=cJSON_GetObjectItemCaseSensitive(root,"internet_ip"),*peer=cJSON_GetObjectItemCaseSensitive(root,"tailnet_target");
            if(boolean(root,"enabled",&c.enabled)&&boolean(root,"notify",&c.notify)
                &&integer(root,"interval_s",3600,&interval)&&integer(root,"failure_threshold",5,&threshold)
                &&integer(root,"gateway_port",65535,&gateway)&&integer(root,"internet_port",65535,&internet)&&integer(root,"tailnet_port",65535,&tailnet)
                &&cJSON_IsString(dns)&&strlen(dns->valuestring)<sizeof c.dns_name
                &&cJSON_IsString(ip)&&strlen(ip->valuestring)<sizeof c.internet_ip
                &&cJSON_IsString(peer)&&strlen(peer->valuestring)<sizeof c.tailnet_target){
                c.interval_s=interval;c.failure_threshold=threshold;c.gateway_port=gateway;c.internet_port=internet;c.tailnet_port=tailnet;
                strcpy(c.dns_name,dns->valuestring);strcpy(c.internet_ip,ip->valuestring);strcpy(c.tailnet_target,peer->valuestring);
                err=health_monitor_set(&c);
            }
        }else if(integer(root,"index",WOL_MAX_DEVICES-1,&index)){
            /* Every indexed mutation is bound to the MAC shown in the UI. */
            const cJSON *mac=cJSON_GetObjectItemCaseSensitive(root,"mac");uint8_t expected[6];wol_device_t d;
            if(cJSON_IsString(mac) && wol_parse_mac(mac->valuestring,expected) && wol_get(index,&d) && !memcmp(expected,d.mac,6)){
                if(!strcmp(action->valuestring,"recover") || !strcmp(action->valuestring,"check"))
                    err=homelab_ops_request(index,!strcmp(action->valuestring,"recover"),false);
                else if(!strcmp(action->valuestring,"device")){
                    ops_device_t p={0};unsigned host,service,timeout,interval,checks,kind,scope;
                    const cJSON *target=cJSON_GetObjectItemCaseSensitive(root,"target");
                    if(cJSON_IsString(target)&&strlen(target->valuestring)<sizeof p.target
                        && boolean(root,"monitor",&p.monitor)&&boolean(root,"notify",&p.notify)
                        && integer(root,"host_port",65535,&host)&&integer(root,"service_port",65535,&service)
                        && integer(root,"timeout_s",600,&timeout)&&integer(root,"interval_s",3600,&interval)
                        && integer(root,"max_checks",60,&checks)&&integer(root,"kind",6,&kind)&&integer(root,"scope",2,&scope)){
                        memcpy(p.mac,expected,6);strcpy(p.target,target->valuestring);p.host_port=host;p.service_port=service;
                        p.timeout_s=timeout;p.interval_s=interval;p.max_checks=checks;p.kind=kind;p.reserved[0]=scope;err=homelab_ops_set_device(index,&p);
                    }
                }
            }
        }
    }
    cJSON_Delete(root);
    if(err!=ESP_OK){httpd_resp_set_status(req,err==ESP_ERR_INVALID_ARG?"400 Bad Request":err==ESP_ERR_INVALID_STATE?"409 Conflict":err==ESP_ERR_TIMEOUT?"429 Too Many Requests"
            :err==ESP_ERR_NO_MEM||err==ESP_ERR_NOT_ALLOWED?"503 Service Unavailable":"500 Internal Server Error");
        /* Plain reasons the page can show as they are. */
        const char *reason=err==ESP_ERR_INVALID_STATE?"Another check or recovery is running; its result appears on this page"
            :err==ESP_ERR_TIMEOUT?"This device was checked less than a minute ago; try again shortly"
            :err==ESP_ERR_NOT_ALLOWED?"Deferred by the resource admission guard: free internal RAM or sockets are below its thresholds"
            :err==ESP_ERR_NO_MEM?"Not enough memory for the optional worker":esp_err_to_name(err);
        cJSON *reply=cJSON_CreateObject();if(reply){cJSON_AddBoolToObject(reply,"ok",false);cJSON_AddStringToObject(reply,"error",reason);}return send_json(req,reply);}
    cJSON *reply=cJSON_CreateObject();if(reply)cJSON_AddBoolToObject(reply,"ok",true);return send_json(req,reply);
}
/* Queue one destination check; the result appears in /api/tailnet-forward. */
static esp_err_t post_service_check(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    char body[96];int total=req->content_len,received=0;esp_err_t err=ESP_ERR_INVALID_ARG;
    if(total>0&&total<(int)sizeof body){
        while(received<total){int n=httpd_req_recv(req,body+received,total-received);if(n<=0)break;received+=n;}
    }
    if(received==total&&total>0&&total<(int)sizeof body){
        body[received]=0;cJSON *root=json_guard_parse(body);unsigned index,token,fields=0;
        for(const cJSON *f=root?root->child:NULL;f;f=f->next)fields++;
        if(cJSON_IsObject(root)&&fields==2&&integer(root,"index",TAILNET_FORWARD_MAX-1,&index)&&integer(root,"rule_token",UINT32_MAX,&token))
            err=service_check_request((int)index,token);
        cJSON_Delete(root);
    }
    cJSON *reply=cJSON_CreateObject();
    if(err!=ESP_OK){
        httpd_resp_set_status(req,err==ESP_ERR_INVALID_STATE?"409 Conflict":err==ESP_ERR_NOT_FINISHED||err==ESP_ERR_TIMEOUT?"429 Too Many Requests":err==ESP_ERR_NO_MEM?"503 Service Unavailable":"400 Bad Request");
        if(reply){cJSON_AddBoolToObject(reply,"ok",false);cJSON_AddStringToObject(reply,"error",err==ESP_ERR_INVALID_STATE?"rule changed; refresh first":err==ESP_ERR_NOT_FINISHED?"another check is running":err==ESP_ERR_TIMEOUT?"checked moments ago; wait a few seconds":err==ESP_ERR_NO_MEM?"optional worker unavailable on this board":"invalid request");}
    } else {httpd_resp_set_status(req,"202 Accepted");if(reply){cJSON_AddBoolToObject(reply,"ok",true);cJSON_AddStringToObject(reply,"state","pending");}}
    return send_json(req,reply);
}
static cJSON *watch_json(void) {
    service_watch_config_t w;service_watch_get(&w);cJSON *o=cJSON_CreateObject();
    if(o&&!(cJSON_AddBoolToObject(o,"enabled",w.enabled)&&cJSON_AddBoolToObject(o,"notify",w.notify)&&cJSON_AddNumberToObject(o,"interval_s",w.interval_s))){cJSON_Delete(o);o=NULL;}
    return o;
}
static esp_err_t get_service_watch(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    return send_json(req,watch_json());
}
static esp_err_t post_service_watch(httpd_req_t *req) {
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    char body[96];int total=req->content_len,received=0;esp_err_t err=ESP_ERR_INVALID_ARG;
    if(total>0&&total<(int)sizeof body)while(received<total){int n=httpd_req_recv(req,body+received,total-received);if(n<=0)break;received+=n;}
    if(total>0&&received==total&&total<(int)sizeof body){
        body[received]=0;cJSON *root=json_guard_parse(body);service_watch_config_t w={0};unsigned interval=0,fields=0;
        for(const cJSON *f=root?root->child:NULL;f;f=f->next)fields++;
        uint8_t enabled=0,notify=0;
        if(cJSON_IsObject(root)&&fields==3&&boolean(root,"enabled",&enabled)&&boolean(root,"notify",&notify)
           &&integer(root,"interval_s",SERVICE_WATCH_MAX_S,&interval)){w.enabled=enabled;w.notify=notify;w.interval_s=interval;err=service_watch_set(&w);}
        cJSON_Delete(root);
    }
    if(err!=ESP_OK){httpd_resp_set_status(req,err==ESP_ERR_INVALID_ARG?"400 Bad Request":err==ESP_ERR_NO_MEM?"503 Service Unavailable":"500 Internal Server Error");
        cJSON *reply=cJSON_CreateObject();if(reply){cJSON_AddBoolToObject(reply,"ok",false);cJSON_AddStringToObject(reply,"error",err==ESP_ERR_INVALID_ARG?"interval must be 60-86400 s":esp_err_to_name(err));}return send_json(req,reply);}
    return send_json(req,watch_json());
}
esp_err_t homelab_ops_register_http(httpd_handle_t server) {
    const httpd_uri_t routes[]={
        {.uri="/api/operations",.method=HTTP_GET,.handler=get_ops},
        {.uri="/api/operations",.method=HTTP_POST,.handler=post_ops},
        {.uri="/api/capabilities",.method=HTTP_GET,.handler=get_capabilities},
        {.uri="/api/health",.method=HTTP_GET,.handler=get_health},
        {.uri="/api/service-leases",.method=HTTP_GET,.handler=get_leases},
        {.uri="/api/diagnostics/export",.method=HTTP_GET,.handler=get_export},
        {.uri="/api/tailnet-forward/check",.method=HTTP_POST,.handler=post_service_check},
        {.uri="/api/service-watch",.method=HTTP_GET,.handler=get_service_watch},
        {.uri="/api/service-watch",.method=HTTP_POST,.handler=post_service_watch}};
    for(unsigned i=0;i<sizeof routes/sizeof routes[0];i++){esp_err_t e=httpd_register_uri_handler(server,&routes[i]);if(e!=ESP_OK)return e;}
    esp_err_t err=service_transfer_register_http(server);
    if(err==ESP_OK)err=config_profiles_register_http(server);
    if(err==ESP_OK)err=eth_uplink_register_http(server);
    if(err==ESP_OK)err=cell_uplink_register_http(server);
    if(err==ESP_OK)err=history_register_http(server);
    if(err==ESP_OK)err=settings_snapshot_register_http(server);
    return err==ESP_OK?layout_migration_register_http(server):err;
}
