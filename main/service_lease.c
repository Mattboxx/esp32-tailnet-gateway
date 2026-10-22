/* Fixed eight-entry leases, immutable packet snapshots and monotonic expiry.
 * Never extend from reboot, clock rollback or a mismatched/reordered rule.
 * SPDX-License-Identifier: MIT */
#include "service_lease.h"
#include "homelab_ops.h"
#include "forwarding_config.h"
#include "nvs.h"
#include "nvs_params.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stddef.h>
#include <time.h>
typedef struct {uint32_t token,created,expires;} lease_t;
typedef struct {uint32_t magic,version;lease_t entries[TAILNET_FORWARD_MAX];uint32_t delete_mask;} lease_store_t;
static lease_store_t saved;
static uint64_t deadlines[TAILNET_FORWARD_MAX];
static bool expired[TAILNET_FORWARD_MAX],ready,loaded;
static uint32_t last_wall;
static uint64_t next_persist_retry;
static SemaphoreHandle_t writer;
static StaticSemaphore_t writer_storage;
static portMUX_TYPE state_lock=portMUX_INITIALIZER_UNLOCKED;
static uint64_t clock_ms(void){return (uint64_t)esp_timer_get_time()/1000;}
/* Stable rule binding, never the current list index. Version 2+ is a strict
 * ledger: once timers are used, new/edited rules require an explicit binding. */
static int lease_index(const lease_store_t *store,uint32_t token) {
    int result=-1;
    for(int i=0;i<TAILNET_FORWARD_MAX;i++)if(store->entries[i].token==token){if(result>=0)return -2;result=i;}
    return result;
}
uint32_t service_lease_token(const tailnet_forward_rule_t *rule) {
    /* Change detection, not a cryptographic identity or authentication token. */
    tailnet_forward_rule_t copy=*rule;copy.valid=copy.enabled=0;memset(copy._reserved,0,sizeof copy._reserved);
    uint32_t h=2166136261u;const uint8_t *bytes=(const uint8_t*)&copy;
    for(unsigned i=0;i<sizeof copy;i++)h=(h^bytes[i])*16777619u;
    return h?h:1;
}
void service_lease_init(void) {
    if(loaded)return;
    writer=xSemaphoreCreateMutexStatic(&writer_storage);
    memset(&saved,0,sizeof saved);saved.magic=0x4c534531;saved.version=1;
    nvs_handle_t nvs;esp_err_t err=nvs_open(NVS_NAMESPACE,NVS_READONLY,&nvs);
    bool usable=err==ESP_ERR_NVS_NOT_FOUND;
    if(err==ESP_OK){lease_store_t candidate={0};size_t size=sizeof candidate;
        err=nvs_get_blob(nvs,"tn_leases",&candidate,&size);
        usable=err==ESP_ERR_NVS_NOT_FOUND;
        bool legacy=(candidate.version==1 || candidate.version==2)&&size==offsetof(lease_store_t,delete_mask);
        bool latest=candidate.version==3&&size==sizeof candidate;
        if(err==ESP_OK && candidate.magic==saved.magic && (legacy || latest)){
            usable=true;
            if(candidate.delete_mask&~((1u<<TAILNET_FORWARD_MAX)-1))usable=false;
            for(unsigned i=0;i<TAILNET_FORWARD_MAX;i++){
                const lease_t *l=&candidate.entries[i];
                bool permanent=candidate.version>=2 && l->token && !l->created && !l->expires;
                if(l->token && !permanent && (l->created<1700000000 || (l->expires && (l->expires<=l->created || l->expires-l->created>604800))))usable=false;
                if(!l->token && (l->created || l->expires))usable=false;
                if(l->token && lease_index(&candidate,l->token)==-2)usable=false;
                if((candidate.delete_mask&(1u<<i))&&(!l->token||!l->created))usable=false;
            }
            if(usable){
                /* Existing v1 timed bindings remain timed by identity. We
                 * cannot infer the identity of formerly untracked rules. */
                if(candidate.version>=2)candidate.version=3;
                for(unsigned i=0;i<TAILNET_FORWARD_MAX;i++)if(candidate.entries[i].token)candidate.version=3;
                saved=candidate;
            }
        }
        nvs_close(nvs);
    }
    portENTER_CRITICAL(&state_lock);ready=usable;loaded=true;portEXIT_CRITICAL(&state_lock);
    (void)service_lease_tick();
}
bool service_lease_tick(void) {
    if(!writer)return false;
    time_t wall=time(NULL);uint64_t now=clock_ms();bool changed=false;unsigned closures=0;
    xSemaphoreTake(writer,portMAX_DELAY);
    portENTER_CRITICAL(&state_lock);
    bool rollback=last_wall && wall>=1700000000 && wall<last_wall;
    if(wall>=1700000000 && wall<=UINT32_MAX && !rollback)last_wall=(uint32_t)wall;
    for(unsigned i=0;i<TAILNET_FORWARD_MAX;i++){
        lease_t l=saved.entries[i];if(!l.token || !l.created || expired[i])continue;
        if(!l.expires || rollback || (wall>=1700000000 && ((uint64_t)wall<l.created || (uint64_t)wall>=l.expires))
            || (deadlines[i] && now>=deadlines[i])){
            if(l.expires)closures++; /* Persisted tombstones do not alert again on boot. */
            expired[i]=true;deadlines[i]=0;changed=true;}
        else if(!deadlines[i] && wall>=1700000000 && wall<=UINT32_MAX){deadlines[i]=now+((uint64_t)l.expires-(uint64_t)wall)*1000;changed=true;}
    }
    lease_store_t candidate=saved;bool persist=false;
    for(unsigned i=0;i<TAILNET_FORWARD_MAX;i++)if(expired[i] && candidate.entries[i].expires){candidate.entries[i].expires=0;persist=true;}
    portEXIT_CRITICAL(&state_lock);
    /* Denial takes effect first. Persist the closed state; never reopen on a
     * failed write. A failed close is retried with bounded NVS backoff. */
    if(persist && now>=next_persist_retry){
        nvs_handle_t nvs;esp_err_t err=nvs_open(NVS_NAMESPACE,NVS_READWRITE,&nvs);
        if(err==ESP_OK){err=nvs_set_blob(nvs,"tn_leases",&candidate,sizeof candidate);if(err==ESP_OK)err=nvs_commit(nvs);nvs_close(nvs);}
        if(err==ESP_OK){portENTER_CRITICAL(&state_lock);saved=candidate;portEXIT_CRITICAL(&state_lock);next_persist_retry=0;}
        else next_persist_retry=now+60000;
    }
    xSemaphoreGive(writer);
    /* Packet denial is already effective, even if persistence/notification fails. */
    if(closures)homelab_ops_service_closed(closures);
    return changed;
}
bool service_lease_allowed(int slot,const tailnet_forward_rule_t *rule) {
    if(slot<0 || slot>=TAILNET_FORWARD_MAX || !rule)return false;
    uint32_t token=service_lease_token(rule);uint64_t now=clock_ms();
    portENTER_CRITICAL(&state_lock);int index=lease_index(&saved,token);
    bool allow=loaded && ready && index==-1 && saved.version==1; /* Untimed legacy table only. */
    if(loaded&&ready&&index>=0){lease_t l=saved.entries[index];
        allow=(!l.created&&!l.expires)||(!expired[index]&&deadlines[index]&&now<deadlines[index]);}
    portEXIT_CRITICAL(&state_lock);return allow;
}
esp_err_t service_lease_set(int slot,uint32_t expected,uint32_t seconds,bool permanent) {
    return service_lease_set_mode(slot,expected,seconds,permanent,false);
}
esp_err_t service_lease_set_mode(int slot,uint32_t expected,uint32_t seconds,bool permanent,bool delete_on_expiry) {
    if(slot<0 || slot>=TAILNET_FORWARD_MAX || (permanent?seconds!=0:seconds<60 || seconds>604800))return ESP_ERR_INVALID_ARG;
    if(permanent&&delete_on_expiry)return ESP_ERR_INVALID_ARG;
    time_t wall=time(NULL);if(!permanent && (wall<1700000000 || (uint64_t)wall>UINT32_MAX-604800))return ESP_ERR_INVALID_STATE;
    forwarding_config_lock();tailnet_forward_rule_t rule;
    if(!tailnet_forward_get(slot,&rule,NULL) || service_lease_token(&rule)!=expected){forwarding_config_unlock();return ESP_ERR_INVALID_STATE;}
    uint32_t live[TAILNET_FORWARD_MAX]={0};int count=tailnet_forward_count();
    for(int i=0;i<count&&i<TAILNET_FORWARD_MAX;i++){tailnet_forward_rule_t r;if(tailnet_forward_get(i,&r,NULL))live[i]=service_lease_token(&r);}
    if(!writer){forwarding_config_unlock();return ESP_ERR_INVALID_STATE;}
    xSemaphoreTake(writer,portMAX_DELAY);
    portENTER_CRITICAL(&state_lock);bool known=ready;lease_store_t candidate=saved;portEXIT_CRITICAL(&state_lock);
    if(!known){xSemaphoreGive(writer);forwarding_config_unlock();return ESP_ERR_INVALID_STATE;}
    if(candidate.version==1){
        /* First opt-in: preserve the exact CURRENT untimed rules explicitly.
         * Later new/edited bindings never silently inherit permanent access. */
        memset(candidate.entries,0,sizeof candidate.entries);
        for(int i=0;i<count&&i<TAILNET_FORWARD_MAX;i++)if(live[i]&&lease_index(&candidate,live[i])<0)
            candidate.entries[i]=(lease_t){.token=live[i]};
        candidate.version=3;
    }
    int record=lease_index(&candidate,expected);
    if(record==-1){
        for(int i=0;i<TAILNET_FORWARD_MAX;i++){
            bool current=false;for(int j=0;j<count&&j<TAILNET_FORWARD_MAX;j++)if(candidate.entries[i].token==live[j])current=true;
            if(!candidate.entries[i].token||!current){record=i;break;} /* Explicit action can recycle an orphan. */
        }
    }
    if(record<0){xSemaphoreGive(writer);forwarding_config_unlock();return ESP_ERR_INVALID_STATE;}
    candidate.entries[record]=permanent?(lease_t){.token=expected}:(lease_t){.token=expected,.created=(uint32_t)wall,.expires=(uint32_t)wall+seconds};
    candidate.delete_mask&=~(1u<<record);
    if(delete_on_expiry)candidate.delete_mask|=1u<<record;
    nvs_handle_t nvs;esp_err_t err=nvs_open(NVS_NAMESPACE,NVS_READWRITE,&nvs);
    if(err==ESP_OK){err=nvs_set_blob(nvs,"tn_leases",&candidate,sizeof candidate);if(err==ESP_OK)err=nvs_commit(nvs);nvs_close(nvs);}
    if(err==ESP_OK){
        portENTER_CRITICAL(&state_lock);saved=candidate;expired[record]=false;
        deadlines[record]=permanent?0:clock_ms()+(uint64_t)seconds*1000;
        if(wall>=1700000000 && wall<=UINT32_MAX)last_wall=(uint32_t)wall;
        portEXIT_CRITICAL(&state_lock);
    }
    xSemaphoreGive(writer);forwarding_config_unlock();return err;
}
bool service_lease_delete_requested(const tailnet_forward_rule_t *rule) {
    if(!rule)return false;
    uint32_t token=service_lease_token(rule);uint64_t now=clock_ms();
    portENTER_CRITICAL(&state_lock);int record=lease_index(&saved,token);
    bool remove=loaded&&ready&&record>=0&&(saved.delete_mask&(1u<<record))&&saved.entries[record].created
        &&(expired[record]||(deadlines[record]&&now>=deadlines[record]));
    portEXIT_CRITICAL(&state_lock);return remove;
}
cJSON *service_lease_snapshot(void) {
    cJSON *arr=cJSON_CreateArray();if(!arr)return NULL;
    for(int i=0;i<tailnet_forward_count();i++){
        tailnet_forward_rule_t rule;if(!tailnet_forward_get(i,&rule,NULL))continue;
        uint32_t token=service_lease_token(&rule);
        portENTER_CRITICAL(&state_lock);int record=lease_index(&saved,token);lease_t l=record>=0?saved.entries[record]:(lease_t){0};
        uint64_t deadline=record>=0?deadlines[record]:0;bool known=ready,done=record>=0&&expired[record],legacy=saved.version==1,remove=record>=0&&(saved.delete_mask&(1u<<record));portEXIT_CRITICAL(&state_lock);
        uint64_t now=clock_ms();bool allow=service_lease_allowed(i,&rule);
        cJSON *item=cJSON_CreateObject();if(!item)break;
        cJSON_AddNumberToObject(item,"index",i);cJSON_AddNumberToObject(item,"rule_token",service_lease_token(&rule));
        cJSON_AddBoolToObject(item,"temporary",l.created!=0);cJSON_AddBoolToObject(item,"effective_enabled",rule.enabled&&allow);
        cJSON_AddBoolToObject(item,"delete_on_expiry",remove);
        cJSON_AddNumberToObject(item,"expires_epoch",l.expires);cJSON_AddNumberToObject(item,"remaining_s",deadline>now?(deadline-now)/1000:0);
        cJSON_AddStringToObject(item,"status",!known?"storage-unavailable":record<0?(legacy?"permanent":"binding-unconfirmed"):!l.created?"permanent":done || (deadline && now>=deadline)?"expired":!deadline?"clock-unavailable":"active");
        cJSON_AddItemToArray(arr,item);
    }
    return arr;
}
