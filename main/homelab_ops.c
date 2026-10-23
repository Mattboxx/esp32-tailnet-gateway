/* Device Registry + Smart Recovery + health evidence + resource admission.
 * One lazy worker, one active job, one probe socket; no reboot or power control.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "homelab_ops.h"
#include "sdkconfig.h"
#include "nvs.h"
#include "nvs_params.h"
#include "web_ui.h"
#include "mqtt_integration.h"
#include "ntfy_integration.h"
#include "tailscale_config.h"
#include "runtime_metrics.h"
#include "snmp_agent.h"
#include "fourvia6.h"
#include "tailnet_forward.h"
#include "service_lease.h"
#include "health_monitor.h"
#include "eth_uplink.h"
#if CONFIG_ETH_SPI_ETHERNET_W5500
#define ETH_MANIFEST_SUMMARY "w5500-spi-conditional"
#else
#define ETH_MANIFEST_SUMMARY "not-compiled"
#endif
#include "service_check.h"
#include "config_profiles.h"
#include "module_supervisor.h"
#include "task_reaper.h"
#include "dns_relay.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_app_desc.h"
#include "esp_system.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_psram.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include "lwip/netdb.h"
#include "esp_wifi.h"
#include "microlink.h"
#include "ml_policy.h"
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define OPS_MAGIC 0x4f505331u
#define OPS_EVENTS 16
#define OPS_STACK 6144
typedef struct {uint32_t magic,version;ops_settings_t settings;ops_device_t devices[WOL_MAX_DEVICES];uint32_t checksum;} ops_store_t;
typedef enum {J_IDLE,J_PRECHECK,J_WAKE,J_WAIT,J_SERVICE,J_REACHABLE,J_TIMEOUT,J_UNKNOWN,J_CANCELLED,J_RESOURCE,J_LEASE_CLOSED} job_state_t;
static const char *const states[]={"idle","precheck","sending-wol","waiting-for-host","checking-service","reachable","not-reachable","inconclusive","cancelled","resource-deferred","service-access-closed"};
typedef struct {uint32_t seq;uint64_t uptime_ms;uint8_t state,index;} event_t;
typedef struct {uint8_t mac[6],state;uint16_t checks;uint32_t latency_ms;uint64_t observed_ms;} result_t;
typedef struct {
    uint32_t id;int index;job_state_t state;bool wake,manual,remote,cancel,host_seen,service_seen,packet_sent,probe_valid;
    uint16_t checks;uint64_t started,deadline,next,finished;
    wol_device_t device;ops_device_t profile;
} job_t;
static ops_store_t store;
static result_t results[WOL_MAX_DEVICES];
static event_t events[OPS_EVENTS];
static uint32_t event_seq,job_seq,denied_jobs;
static uint32_t service_closures;
static module_supervisor_t supervisor;  /* worker-owned */
static job_t job;
static SemaphoreHandle_t lock;
static StaticSemaphore_t lock_storage;
static portMUX_TYPE init_lock=portMUX_INITIALIZER_UNLOCKED;
static bool initialized,starting;
static TaskHandle_t task;
static StaticTask_t task_storage;
static struct {uint8_t mac[6];uint64_t time;} last_manual[WOL_MAX_DEVICES];
static uint64_t next_monitor;
static unsigned monitor_index;
static void worker(void *arg);
static esp_err_t ensure_worker(void);
extern bool wifi_ap_runtime_enabled(void);
#define LOCK() xSemaphoreTake(lock,portMAX_DELAY)
#define UNLOCK() xSemaphoreGive(lock)
static uint64_t now_ms(void) {return (uint64_t)esp_timer_get_time()/1000;}
static bool active(job_state_t s) {return s>=J_PRECHECK && s<=J_SERVICE;}
static uint32_t checksum(const ops_store_t *s) {
    uint32_t hash=2166136261u;const uint8_t *p=(const uint8_t*)s;
    for(size_t i=0;i<offsetof(ops_store_t,checksum);i++)hash=(hash^p[i])*16777619u;
    return hash;
}
static bool valid_settings(const ops_settings_t *s) {
    return s && s->monitoring<=1 && s->guard<=1 && s->remote_commands<=1 && s->lease_notifications<=1
        && s->minimum_internal<=262144 && s->minimum_largest<=131072
        && s->socket_reserve<=CONFIG_LWIP_MAX_SOCKETS && s->interval_s>=30 && s->interval_s<=3600;
}
static bool valid_profile(const ops_device_t *p) {
    if(!p || p->monitor>1 || p->notify>1 || p->kind>6 || p->reserved[0]>2 || !memchr(p->target,0,sizeof p->target)
        || p->timeout_s<5 || p->timeout_s>600 || p->interval_s<30 || p->interval_s>3600
        || !p->max_checks || p->max_checks>60 || (p->target[0] && !p->host_port))return false;
    for(const unsigned char *c=(const unsigned char*)p->target;*c;c++)
        if(!((*c>='a'&&*c<='z')||(*c>='A'&&*c<='Z')||(*c>='0'&&*c<='9')||*c=='-'||*c=='.'))return false;
    return true;
}
static void event_locked(unsigned state,unsigned index) {
    event_t *e=&events[event_seq%OPS_EVENTS];e->seq=++event_seq;e->uptime_ms=now_ms();e->state=state;e->index=index;
}
static esp_err_t save_locked(ops_store_t *candidate) {
    candidate->checksum=checksum(candidate);nvs_handle_t nvs;
    esp_err_t err=nvs_open(NVS_NAMESPACE,NVS_READWRITE,&nvs);
    if(err==ESP_OK){err=nvs_set_blob(nvs,"ops_registry",candidate,sizeof *candidate);if(err==ESP_OK)err=nvs_commit(nvs);nvs_close(nvs);}
    if(err==ESP_OK)store=*candidate;
    return err;
}
void homelab_ops_init(void) {
    portENTER_CRITICAL(&init_lock);
    if(!lock)lock=xSemaphoreCreateMutexStatic(&lock_storage);
    portEXIT_CRITICAL(&init_lock);
    LOCK();if(initialized){UNLOCK();return;}
    memset(&store,0,sizeof store);store.magic=OPS_MAGIC;store.version=1;
    store.settings=(ops_settings_t){.interval_s=60,.minimum_internal=16384,.minimum_largest=8192,.socket_reserve=4};
    nvs_handle_t nvs;size_t size=sizeof store;
    ops_store_t *loaded=heap_caps_calloc(1,sizeof *loaded,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(loaded && nvs_open(NVS_NAMESPACE,NVS_READONLY,&nvs)==ESP_OK){
        bool valid=nvs_get_blob(nvs,"ops_registry",loaded,&size)==ESP_OK && size==sizeof *loaded
            && loaded->magic==OPS_MAGIC && loaded->version==1 && loaded->checksum==checksum(loaded) && valid_settings(&loaded->settings);
        for(unsigned i=0;i<WOL_MAX_DEVICES && valid;i++)if(loaded->devices[i].target[0] || loaded->devices[i].mac[0] || loaded->devices[i].timeout_s)
            valid=valid_profile(&loaded->devices[i]);
        if(valid)store=*loaded;
        nvs_close(nvs);
    }
    free(loaded);initialized=true;bool monitoring=store.settings.monitoring;UNLOCK();
    health_monitor_init();
    if(monitoring||health_monitor_enabled())(void)ensure_worker();
}
static int find_profile_locked(const uint8_t mac[6]) {
    for(int i=0;i<WOL_MAX_DEVICES;i++)if(store.devices[i].timeout_s && !memcmp(store.devices[i].mac,mac,6))return i;
    return -1;
}
bool homelab_ops_device(int index,ops_device_t *out) {
    if(!out)return false;
    wol_device_t device;if(!wol_get(index,&device))return false;
    homelab_ops_init();LOCK();int i=find_profile_locked(device.mac);
    if(i>=0)*out=store.devices[i];else{
        memset(out,0,sizeof *out);memcpy(out->mac,device.mac,6);out->host_port=22;out->timeout_s=120;out->max_checks=20;out->interval_s=60;
    }
    UNLOCK();return true;
}
esp_err_t homelab_ops_set_device(int index,const ops_device_t *profile) {
    wol_device_t device;if(!profile || !wol_get(index,&device) || memcmp(device.mac,profile->mac,6) || !valid_profile(profile))return ESP_ERR_INVALID_ARG;
    homelab_ops_init();ops_store_t *candidate=heap_caps_malloc(sizeof *candidate,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!candidate)return ESP_ERR_NO_MEM;
    uint8_t saved[WOL_MAX_DEVICES][6];int count=wol_count();
    for(int i=0;i<count;i++){wol_device_t d;if(wol_get(i,&d))memcpy(saved[i],d.mac,6);else memset(saved[i],0,6);}
    LOCK();if(active(job.state)){UNLOCK();free(candidate);return ESP_ERR_INVALID_STATE;}
    *candidate=store;int slot=find_profile_locked(device.mac);
    if(slot<0)for(int i=0;i<WOL_MAX_DEVICES;i++)if(!candidate->devices[i].timeout_s){slot=i;break;}
    if(slot<0)for(int i=0;i<WOL_MAX_DEVICES;i++){
        bool present=false;for(int j=0;j<count;j++)if(!memcmp(candidate->devices[i].mac,saved[j],6))present=true;
        if(!present){slot=i;break;}
    }
    if(slot<0){UNLOCK();free(candidate);return ESP_ERR_NO_MEM;}
    candidate->devices[slot]=*profile;esp_err_t err=save_locked(candidate);UNLOCK();free(candidate);return err;
}
void homelab_ops_settings(ops_settings_t *out) {homelab_ops_init();LOCK();*out=store.settings;UNLOCK();}
void homelab_ops_service_closed(unsigned count) {
    if(!count || count>TAILNET_FORWARD_MAX)return;
    homelab_ops_init();LOCK();
    service_closures=UINT32_MAX-service_closures<count?UINT32_MAX:service_closures+count;
    event_locked(J_LEASE_CLOSED,count);
    bool notify=store.settings.lease_notifications;
    UNLOCK();
    mqtt_integration_publish_now();
    if(notify){char message[128];snprintf(message,sizeof message,
        "%u temporary service rule(s) closed: deadline reached or clock validity lost. Check local Service Gateway.",count);
        (void)ntfy_integration_queue_event(message);}
}
void homelab_ops_resources(ops_resources_t *out) {
    if(!out)return;
    homelab_ops_init();
    memset(out,0,sizeof *out);out->internal_free=heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    out->internal_min=heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);out->internal_largest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
    out->psram_free=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);out->psram_min=heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM);
    out->psram_largest=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
    out->socket_limit=CONFIG_LWIP_MAX_SOCKETS;out->sockets_used=0;
    for(int i=0;i<CONFIG_LWIP_MAX_SOCKETS;i++){int type;socklen_t size=sizeof type;
        if(getsockopt(LWIP_SOCKET_OFFSET+i,SOL_SOCKET,SO_TYPE,&type,&size)==0)out->sockets_used++;}
    LOCK();TaskHandle_t handle=task;UNLOCK();out->worker_running=handle!=NULL;
    if(handle)out->worker_stack_min=uxTaskGetStackHighWaterMark(handle);
}
bool homelab_ops_admit(void) {
    ops_settings_t settings;homelab_ops_settings(&settings);if(!settings.guard)return true;
    ops_resources_t r;homelab_ops_resources(&r);
    bool allowed=r.internal_free>=settings.minimum_internal && r.internal_largest>=settings.minimum_largest
        && r.socket_limit-r.sockets_used>settings.socket_reserve;
    if(!allowed){LOCK();denied_jobs++;UNLOCK();}return allowed;
}
static esp_err_t ensure_worker(void) {
#if !defined(CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM) || !CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM
    /* Never assert at runtime or silently consume the routing heap. */
    return ESP_ERR_NOT_SUPPORTED;
#endif
    homelab_ops_init();LOCK();
    if(task){UNLOCK();return ESP_OK;}if(starting){UNLOCK();return ESP_ERR_INVALID_STATE;}starting=true;UNLOCK();
    /* PSRAM is explicit; optional worker must not take the scarce routing heap. */
    StackType_t *stack=heap_caps_malloc(OPS_STACK,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    TaskHandle_t created=stack ? xTaskCreateStaticPinnedToCore(worker,"homelab_ops",OPS_STACK,NULL,2,stack,&task_storage,tskNO_AFFINITY) : NULL;
    LOCK();task=created;starting=false;UNLOCK();
    if(!created)free(stack);
    return created?ESP_OK:ESP_ERR_NO_MEM;
}
esp_err_t homelab_ops_set_settings(const ops_settings_t *settings) {
    if(!valid_settings(settings))return ESP_ERR_INVALID_ARG;
    homelab_ops_init();
    if(settings->monitoring && ensure_worker()!=ESP_OK)return ESP_ERR_NO_MEM;
    ops_store_t *candidate=heap_caps_malloc(sizeof *candidate,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!candidate)return ESP_ERR_NO_MEM;
    LOCK();*candidate=store;candidate->settings=*settings;esp_err_t err=save_locked(candidate);UNLOCK();free(candidate);return err;
}
esp_err_t homelab_ops_start_optional_worker(void) {return ensure_worker();}
esp_err_t homelab_ops_request(int index,bool wake,bool remote) {
    ops_device_t profile;wol_device_t device;
    if(index<0 || index>=WOL_MAX_DEVICES || !homelab_ops_device(index,&profile) || !wol_get(index,&device)
        || memcmp(profile.mac,device.mac,6))return ESP_ERR_INVALID_ARG;
    if(wake && profile.max_checks<2)return ESP_ERR_INVALID_ARG;
    ops_settings_t settings;homelab_ops_settings(&settings);
    if(remote && !settings.remote_commands)return ESP_ERR_NOT_SUPPORTED;
    if(!homelab_ops_admit())return ESP_ERR_NO_MEM;
    esp_err_t err=ensure_worker();if(err!=ESP_OK)return err;
    uint64_t now=now_ms();LOCK();
    int cooldown=-1,oldest=0;
    for(int i=0;i<WOL_MAX_DEVICES;i++){
        if(!memcmp(last_manual[i].mac,device.mac,6))cooldown=i;
        if(last_manual[i].time<last_manual[oldest].time)oldest=i;
    }
    if(active(job.state) || (cooldown>=0 && now-last_manual[cooldown].time<60000)){UNLOCK();return ESP_ERR_INVALID_STATE;}
    job=(job_t){.id=++job_seq,.index=index,.state=J_PRECHECK,.wake=wake,.manual=true,.remote=remote,.started=now,
        .deadline=now+(uint64_t)profile.timeout_s*1000,.device=device,.profile=profile};
    if(cooldown<0)cooldown=oldest;
    memcpy(last_manual[cooldown].mac,device.mac,6);last_manual[cooldown].time=now;
    event_locked(J_PRECHECK,index);UNLOCK();return ESP_OK;
}
esp_err_t homelab_ops_cancel(void) {homelab_ops_init();LOCK();bool running=active(job.state);if(running)job.cancel=true;UNLOCK();return running?ESP_OK:ESP_ERR_INVALID_STATE;}
esp_err_t homelab_ops_command(const char *selector,bool wake) {
    uint8_t mac[6];if(!wol_parse_mac(selector,mac))return ESP_ERR_INVALID_ARG;
    for(int i=0;i<wol_count();i++){wol_device_t d;if(wol_get(i,&d)&&!memcmp(mac,d.mac,6))return homelab_ops_request(i,wake,true);}
    return ESP_ERR_NOT_FOUND;
}
/* One TCP probe per worker; serialized SDK DNS uses finite retry limits.
 * An in-flight resolver can outlast a job deadline; it never blocks TCPIP. */
static int connect_probe(const ops_device_t *p,uint16_t port,uint32_t *latency) {
    if(!p->target[0] || !port)return -1;
    struct sockaddr_in address={.sin_family=AF_INET,.sin_port=htons(port)};
    if(inet_pton(AF_INET,p->target,&address.sin_addr)!=1){
        microlink_t *ml=tailscale_get_microlink();uint32_t ip=ml?microlink_resolve(ml,p->target):0;
        if(ip)address.sin_addr.s_addr=htonl(ip);
        else{
            struct addrinfo hints={.ai_family=AF_INET,.ai_socktype=SOCK_STREAM},*answer=NULL;
            if(getaddrinfo(p->target,NULL,&hints,&answer)!=0 || !answer){if(answer)freeaddrinfo(answer);return -1;}
            address.sin_addr=((struct sockaddr_in*)answer->ai_addr)->sin_addr;freeaddrinfo(answer);
        }
    }
    uint32_t ip=ntohl(address.sin_addr.s_addr);
    if(!ip || (ip>>24)==127 || (ip>>24)>=224 || (ip>>24)==0)return -1;
    if(p->reserved[0]==1){
        esp_netif_t *sta=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");esp_netif_ip_info_t info={0};
        if(!sta || !esp_netif_is_netif_up(sta) || esp_netif_get_ip_info(sta,&info)!=ESP_OK
            || !info.ip.addr || (address.sin_addr.s_addr&info.netmask.addr)!=(info.ip.addr&info.netmask.addr))return -1;
    }else if(p->reserved[0]==2 && (!tailscale_is_connected() || (ip&0xffc00000u)!=0x64400000u))return -1;
    LOCK();bool proceed=!job.cancel && (!job.remote || store.settings.remote_commands) && now_ms()<job.deadline;UNLOCK();
    if(!proceed)return -1;
    int fd=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);if(fd<0)return -1;
    int flags=fcntl(fd,F_GETFL,0);if(flags<0 || fcntl(fd,F_SETFL,flags|O_NONBLOCK)<0){close(fd);return -1;}
    uint64_t began=now_ms();int connected=connect(fd,(struct sockaddr*)&address,sizeof address);
    if(connected<0 && errno!=EINPROGRESS){close(fd);return 0;}
    fd_set writable;FD_ZERO(&writable);FD_SET(fd,&writable);struct timeval timeout={.tv_sec=1,.tv_usec=0};
    int ready=select(fd+1,NULL,&writable,NULL,&timeout),error=0;socklen_t size=sizeof error;
    bool ok=ready>0 && getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&size)==0 && !error;
    *latency=(uint32_t)(now_ms()-began);close(fd);return ok?1:0;
}
static void finish_locked(job_state_t state) {
    job.state=state;job.finished=now_ms();uint32_t latency=results[job.index].latency_ms;
    results[job.index]=(result_t){.state=state,.checks=job.checks,.latency_ms=latency,.observed_ms=now_ms()};
    memcpy(results[job.index].mac,job.device.mac,6);
    event_locked(state,job.index);
}
static void apply_probe_locked(const job_t *local,int result,uint32_t latency) {
    if(job.id!=local->id)return;
    job.checks++;results[job.index].latency_ms=latency;
    if(result>=0)job.probe_valid=true;
    if(job.cancel || (job.remote && !store.settings.remote_commands))finish_locked(J_CANCELLED);
    else if(now_ms()>=job.deadline)finish_locked(job.host_seen || !job.probe_valid?J_UNKNOWN:J_TIMEOUT);
    else if(result<0){
        /* A sleeping host may not answer DNS. An explicitly authorized WoL
         * remains useful, but cannot be reported as a verified recovery. */
        if(local->state==J_PRECHECK && local->wake){job.state=J_WAKE;job.next=now_ms();}
        else if(local->manual && local->packet_sent){job.state=J_WAIT;job.next=now_ms()+3000;}
        else finish_locked(J_UNKNOWN);
    }
    else if(result>0){
        if(local->state==J_SERVICE || !local->profile.service_port){job.host_seen=true;job.service_seen=local->state==J_SERVICE;finish_locked(J_REACHABLE);}
        else{job.host_seen=true;job.state=J_SERVICE;job.next=now_ms()+1000;}
    }else if(local->state==J_PRECHECK && local->wake){job.state=J_WAKE;job.next=now_ms();}
    else if(!local->manual)finish_locked(J_TIMEOUT);
    else{job.state=local->state==J_SERVICE?J_SERVICE:J_WAIT;job.next=now_ms()+3000;}
}
static void worker(void *arg) {
    (void)arg;
    uint32_t notified=0;
    for(;;){
        vTaskDelay(pdMS_TO_TICKS(200));
        uint64_t now=now_ms();job_t local;LOCK();bool ready=task!=NULL;local=job;ops_settings_t settings=store.settings;UNLOCK();
        if(!ready)continue;
        if(local.remote && !settings.remote_commands)local.cancel=true;
        if(local.id && !active(local.state) && local.id!=notified){
            notified=local.id;
            if(local.profile.notify){char message[192];snprintf(message,sizeof message,"Recovery/check #%lu: %s. WoL send %s; host verified: %s; service verified: %s. Send is not proof of boot.",
                (unsigned long)local.id,states[local.state],local.packet_sent?"confirmed locally":"not confirmed (partial send possible)",local.host_seen?"yes":"no",local.service_seen?"yes":"no");
                (void)ntfy_integration_queue_event(message);}
            mqtt_integration_publish_now();
        }
        {   /* Optional integration workers that failed to start get bounded retries. */
            ntfy_integration_status_t ntfy;ntfy_integration_get_status(&ntfy);
            bool running=mqtt_integration_task_running()&&ntfy.task_running;
            if(module_supervisor_due(&supervisor,now,running)){
                unsigned restarted=0;
                if(!mqtt_integration_task_running()){mqtt_integration_init();restarted+=mqtt_integration_task_running();}
                if(!ntfy.task_running){ntfy_integration_init();ntfy_integration_get_status(&ntfy);restarted+=ntfy.task_running;}
                LOCK();module_supervisor_result(&supervisor,now,restarted,mqtt_integration_task_running()&&ntfy.task_running);UNLOCK();
            }
        }
        if(!active(local.state)){
            health_monitor_poll(); /* Serialized with recovery; at most one probe. */
            service_check_poll();  /* Same worker and socket budget, on request only. */
            if(!settings.monitoring || now<next_monitor)continue;
            next_monitor=now+(uint64_t)settings.interval_s*1000;
            int count=wol_count();if(!count)continue;
            int index=(int)(monitor_index++%(unsigned)count);ops_device_t p;wol_device_t d;
            if(!homelab_ops_device(index,&p)||!p.monitor||!wol_get(index,&d)||!homelab_ops_admit())continue;
            LOCK();uint64_t observed=results[index].observed_ms;UNLOCK();
            if(observed && now-observed<(uint64_t)p.interval_s*1000)continue;
            LOCK();if(!active(job.state))job=(job_t){.id=++job_seq,.index=index,.state=J_PRECHECK,.started=now,
                .deadline=now+3000,.device=d,.profile=p};UNLOCK();continue;
        }
        if(local.cancel || now>=local.deadline || local.checks>=local.profile.max_checks){
            LOCK();if(job.id==local.id)finish_locked(local.cancel?J_CANCELLED:local.host_seen || !local.probe_valid?J_UNKNOWN:J_TIMEOUT);UNLOCK();continue;
        }
        if(now<local.next)continue;
        if(!homelab_ops_admit()){LOCK();if(job.id==local.id)finish_locked(J_RESOURCE);UNLOCK();continue;}
        if(local.state==J_WAKE){
            LOCK();bool permitted=job.id==local.id && !job.cancel;UNLOCK();
            esp_err_t err=permitted?wol_send_mac(local.device.mac,local.device.broadcast,local.device.port):ESP_ERR_INVALID_STATE;
            LOCK();if(job.id==local.id){job.packet_sent=err==ESP_OK;job.state=J_WAIT;job.next=now_ms()+3000;
                if(err!=ESP_OK || !local.profile.target[0])finish_locked(J_UNKNOWN);else event_locked(J_WAIT,job.index);}UNLOCK();continue;
        }
        uint32_t latency=0;int result=connect_probe(&local.profile,local.state==J_SERVICE?local.profile.service_port:local.profile.host_port,&latency);
        LOCK();
        apply_probe_locked(&local,result,latency);
        UNLOCK();
        mqtt_integration_publish_now(); /* Queued flag; routing never waits for broker. */
    }
}
cJSON *homelab_ops_snapshot(bool detailed) {
    homelab_ops_init();ops_resources_t r;homelab_ops_resources(&r);
    cJSON *root=cJSON_CreateObject();if(!root)return NULL;
    cJSON_AddNumberToObject(root,"internal_free",r.internal_free);cJSON_AddNumberToObject(root,"internal_min",r.internal_min);
    cJSON_AddNumberToObject(root,"internal_largest",r.internal_largest);cJSON_AddNumberToObject(root,"psram_free",r.psram_free);
    cJSON_AddNumberToObject(root,"psram_min",r.psram_min);cJSON_AddNumberToObject(root,"sockets_used",r.sockets_used);
    cJSON_AddNumberToObject(root,"psram_largest",r.psram_largest);
    ml_policy_status_t policy;ml_policy_get_status(&policy);
    cJSON_AddBoolToObject(root,"authority_ready",policy.authority_ready);
    cJSON_AddBoolToObject(root,"peer_authority",policy.peer_authority);cJSON_AddBoolToObject(root,"filter_authority",policy.filter_authority);
    cJSON_AddNumberToObject(root,"policy_expanded_rules",policy.expanded_rules);cJSON_AddNumberToObject(root,"policy_peer_count",policy.peers);
    cJSON_AddNumberToObject(root,"return_flow_count",policy.return_flows);
    cJSON_AddNumberToObject(root,"socket_limit",r.socket_limit);cJSON_AddBoolToObject(root,"worker_running",r.worker_running);
    if(r.worker_running)cJSON_AddNumberToObject(root,"worker_stack_min_raw",r.worker_stack_min);
    esp_netif_t *sta=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");wifi_ap_record_t ap;
    cJSON_AddBoolToObject(root,"wifi_associated",esp_wifi_sta_get_ap_info(&ap)==ESP_OK);
    cJSON_AddBoolToObject(root,"local_uplink_available",sta && esp_netif_is_netif_up(sta));
    cJSON_AddBoolToObject(root,"control_connected",tailscale_is_connected());
    cJSON_AddStringToObject(root,"data_plane","not-verified");
    cJSON *health=health_monitor_snapshot(detailed);
    if(!health||!cJSON_AddItemToObject(root,"health",health)){cJSON_Delete(health);cJSON_Delete(root);return NULL;}
    cJSON_AddStringToObject(root,"internet","not-verified");cJSON_AddStringToObject(root,"dns","not-verified");
    LOCK();job_t j=job;ops_settings_t s=store.settings;uint32_t denied=denied_jobs;
    cJSON_AddStringToObject(root,"recovery_state",states[j.state]);cJSON_AddNumberToObject(root,"job_id",j.id);
    cJSON_AddNumberToObject(root,"device_index",j.index);cJSON_AddBoolToObject(root,"packet_sent",j.packet_sent);
    cJSON_AddBoolToObject(root,"host_verified",j.host_seen);cJSON_AddBoolToObject(root,"service_verified",j.service_seen);
    cJSON_AddNumberToObject(root,"checks",j.checks);cJSON_AddNumberToObject(root,"denied_jobs",denied);
    cJSON_AddNumberToObject(root,"duration_ms",j.id?(j.finished?j.finished:now_ms())-j.started:0);
    cJSON_AddBoolToObject(root,"monitoring",s.monitoring);cJSON_AddBoolToObject(root,"guard",s.guard);
    cJSON_AddBoolToObject(root,"resource_thresholds_calibrated",false);
    cJSON_AddBoolToObject(root,"remote_commands",s.remote_commands);
    cJSON_AddBoolToObject(root,"lease_notifications",s.lease_notifications);
    cJSON_AddNumberToObject(root,"service_closures",service_closures);
    cJSON_AddNumberToObject(root,"module_restarts",supervisor.restarts);
    cJSON_AddNumberToObject(root,"task_reaper_pending",task_reaper_pending());cJSON_AddNumberToObject(root,"task_reaper_fallbacks",task_reaper_fallbacks());cJSON_AddNumberToObject(root,"task_reaper_reaped",task_reaper_reaped());
    cJSON_AddNumberToObject(root,"minimum_internal",s.minimum_internal);cJSON_AddNumberToObject(root,"minimum_largest",s.minimum_largest);
    cJSON_AddNumberToObject(root,"socket_reserve",s.socket_reserve);cJSON_AddNumberToObject(root,"interval_s",s.interval_s);
    cJSON *history=cJSON_AddArrayToObject(root,"events");
    for(unsigned i=0;history && i<OPS_EVENTS;i++)if(events[i].seq){cJSON *e=cJSON_CreateObject();if(!e)continue;
        cJSON_AddNumberToObject(e,"sequence",events[i].seq);cJSON_AddNumberToObject(e,"uptime_ms",events[i].uptime_ms);
        cJSON_AddStringToObject(e,"state",states[events[i].state]);
        if(events[i].state==J_LEASE_CLOSED)cJSON_AddNumberToObject(e,"rule_count",events[i].index);
        else if(detailed)cJSON_AddNumberToObject(e,"device_index",events[i].index);
        cJSON_AddItemToArray(history,e);}
    UNLOCK();
    if(detailed){
        cJSON *leases=service_lease_snapshot();
        if(!leases || !cJSON_AddItemToObject(root,"forwarding_leases",leases)){
            cJSON_Delete(leases);cJSON_Delete(root);return NULL;
        }
        cJSON *devices=cJSON_AddArrayToObject(root,"devices");
        for(int i=0;devices && i<wol_count();i++){wol_device_t d;ops_device_t p;if(!wol_get(i,&d)||!homelab_ops_device(i,&p))continue;
            cJSON *item=cJSON_CreateObject();if(!item)continue;char mac[18];wol_format_mac(d.mac,mac);
            cJSON_AddNumberToObject(item,"index",i);cJSON_AddStringToObject(item,"mac",mac);cJSON_AddStringToObject(item,"name",d.name);
            cJSON_AddStringToObject(item,"target",p.target);cJSON_AddNumberToObject(item,"host_port",p.host_port);cJSON_AddNumberToObject(item,"service_port",p.service_port);
            cJSON_AddNumberToObject(item,"timeout_s",p.timeout_s);cJSON_AddNumberToObject(item,"interval_s",p.interval_s);cJSON_AddNumberToObject(item,"max_checks",p.max_checks);
            cJSON_AddBoolToObject(item,"monitor",p.monitor);cJSON_AddBoolToObject(item,"notify",p.notify);cJSON_AddNumberToObject(item,"kind",p.kind);
            cJSON_AddNumberToObject(item,"scope",p.reserved[0]);
            LOCK();result_t rt=results[i];UNLOCK();
            if(memcmp(rt.mac,d.mac,6))memset(&rt,0,sizeof rt);
            cJSON_AddStringToObject(item,"state",states[rt.state]);cJSON_AddNumberToObject(item,"observed_ms",rt.observed_ms);
            cJSON_AddNumberToObject(item,"latency_ms",rt.latency_ms);cJSON_AddStringToObject(item,"check_method","tcp-connect");
            cJSON_AddItemToArray(devices,item);
        }
    }else{cJSON_DeleteItemFromObject(root,"device_index");}
    return root;
}
/* Null means unobserved, never silently false. This is runtime evidence, not
 * end-to-end qualification or network-policy authorization. */
static bool capability_add(cJSON *array,const char *id,bool compiled,int hardware,
                           int configured,int running,bool experimental,const char *reason) {
    cJSON *item=cJSON_CreateObject();if(!item)return false;
    bool ok=cJSON_AddStringToObject(item,"id",id)
        &&cJSON_AddBoolToObject(item,"compiled",compiled)
        &&(hardware<0?cJSON_AddNullToObject(item,"hardware_supported"):cJSON_AddBoolToObject(item,"hardware_supported",hardware))
        &&(configured<0?cJSON_AddNullToObject(item,"configured"):cJSON_AddBoolToObject(item,"configured",configured))
        &&(running<0?cJSON_AddNullToObject(item,"active"):cJSON_AddBoolToObject(item,"active",running))
        &&cJSON_AddBoolToObject(item,"experimental",experimental)
        &&cJSON_AddBoolToObject(item,"verified",false)
        &&cJSON_AddStringToObject(item,"evidence",reason);
    if(!ok||!cJSON_AddItemToArray(array,item)){cJSON_Delete(item);return false;}
    return true;
}
cJSON *homelab_ops_capabilities(void) {
    cJSON *root=cJSON_CreateObject();if(!root)return NULL;
    const esp_app_desc_t *app=esp_app_get_description();
    esp_chip_info_t chip;esp_chip_info(&chip);uint32_t flash=0;
    bool wifi=(chip.features&CHIP_FEATURE_WIFI_BGN)!=0;
    size_t psram=esp_psram_get_size();
    bool ok=cJSON_AddNumberToObject(root,"schema",2)
        &&cJSON_AddStringToObject(root,"product","ESP32 Tailnet Gateway — Mattboxx Edition")
        &&cJSON_AddStringToObject(root,"version",app?app->version:"unknown")
        &&cJSON_AddBoolToObject(root,"hardware_qualified",false)
        &&cJSON_AddBoolToObject(root,"policy_parity_verified",false)
        &&cJSON_AddNumberToObject(root,"chip_model",chip.model)
        &&cJSON_AddNumberToObject(root,"cores",chip.cores)
        &&cJSON_AddNumberToObject(root,"psram_bytes",psram);
    if(esp_flash_get_size(NULL,&flash)==ESP_OK)ok=ok&&cJSON_AddNumberToObject(root,"flash_bytes",flash);
    else ok=ok&&cJSON_AddNullToObject(root,"flash_bytes");
    cJSON *arr=ok?cJSON_AddArrayToObject(root,"features"):NULL;
    if(!arr){cJSON_Delete(root);return NULL;}
    ops_settings_t settings;homelab_ops_settings(&settings);
    mqtt_integration_config_t mqtt;mqtt_integration_get_config(&mqtt);
    ntfy_integration_config_t ntfy;ntfy_integration_get_config(&ntfy);
    fourvia6_status_t v6;fourvia6_get_status(&v6);
    ml_policy_status_t policy;ml_policy_get_status(&policy);
    uint32_t enabled=0,installed=0;tailnet_forward_totals(&enabled,&installed,NULL,NULL);
    LOCK();bool worker_running=task!=NULL,recovery_active=active(job.state);UNLOCK();
    esp_netif_t *sta=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");esp_netif_ip_info_t ip={0};
    bool sta_address=sta&&esp_netif_get_ip_info(sta,&ip)==ESP_OK&&ip.ip.addr;
    const char *capabilities[]={"tailscale","headscale","direct","derp","wifi-uplink","ethernet","ipv6",
        "subnet-routing","exit-node","ap-gateway","lan-tailnet-forwarding","temporary-services",
        "service-rule-transfer","4via6","dns-relay","firewall","wol","smart-recovery","health",
        "resource-guard","mqtt","home-assistant","ntfy","snmp","ota","diagnostic-export","web-ui",
        "destination-test","service-watch","profiles"};
    service_watch_config_t watch;service_watch_get(&watch);
    profile_id_t profile;bool profile_rollback;config_profiles_status(&profile,&profile_rollback);
    for(unsigned i=0;i<sizeof capabilities/sizeof capabilities[0];i++){
        const char *id=capabilities[i],*reason="Compiled; runtime path has not been observed.";
        bool compiled=true,experimental=false;int hardware=1,configured=-1,running=-1;
        if(!strcmp(id,"tailscale")){configured=tailscale_enabled;running=configured&&tailscale_is_connected();reason="Control connection is not proof of peer/service reachability.";}
        else if(!strcmp(id,"headscale")){configured=tailscale_enabled&&tailscale_login_server&&tailscale_login_server[0];running=configured&&tailscale_is_connected();reason="Custom control URL selected; server compatibility is not automatically verified.";}
        else if(!strcmp(id,"direct")||!strcmp(id,"derp")){configured=tailscale_enabled;reason="Transport support; no fresh per-peer path proof in this manifest.";}
        else if(!strcmp(id,"wifi-uplink")){hardware=wifi;configured=wifi?1:0;running=sta_address;reason="STA address observed; association/address alone do not prove Internet access.";}
        else if(!strcmp(id,"ethernet")){eth_status_t eth;eth_uplink_get_status(&eth);compiled=eth.compiled;
            hardware=eth.driver_started?1:eth.enabled_at_boot&&eth.error[0]?0:-1;configured=eth.enabled_at_boot;running=eth.has_ip;experimental=true;
            reason="W5500 SPI module with explicit pins only; link/IP observed, not physically validated; service listeners and health checks follow the selected uplink";}
        else if(!strcmp(id,"ipv6")){
#if CONFIG_LWIP_IPV6
            configured=1;
#else
            compiled=false;configured=running=0;
#endif
            reason="Build setting only; no native IPv6 end-to-end compatibility claim.";
        }
        else if(!strcmp(id,"subnet-routing")){configured=tailscale_enabled&&(tailscale_advertise_ap||(tailscale_advertise_routes&&tailscale_advertise_routes[0]));reason="Saved route intent; controller approval and packet traversal are unobserved.";}
        else if(!strcmp(id,"exit-node")){configured=tailscale_advertise_exit_node;running=tailscale_exit_server_active();reason="Boot-time IPv4 exit service state, not controller approval or verified Internet egress.";}
        else if(!strcmp(id,"ap-gateway")){hardware=wifi;running=wifi_ap_runtime_enabled();reason="AP runtime state; saved AP policy and current client reachability are separate.";}
        else if(!strcmp(id,"lan-tailnet-forwarding")){hardware=psram>0;configured=tailnet_forward_count()>0;running=installed>0;reason="Installed mapping count, not remote service verification.";}
        else if(!strcmp(id,"temporary-services")){configured=tailnet_forward_count()>0;reason="Fail-closed lease engine compiled; individual bindings require their own lease snapshot.";}
        else if(!strcmp(id,"service-rule-transfer")){hardware=psram>0;configured=1;reason="Configuration-only export; import requires preview/confirmation and forces rules OFF.";}
        else if(!strcmp(id,"4via6")){configured=v6.enabled;reason="Saved configuration; translation interoperability unverified.";}
        else if(!strcmp(id,"dns-relay")){configured=dns_relay_is_enabled();running=dns_relay_is_healthy();reason="Local DNS listener health, not proof that an upstream resolver answers.";}
        else if(!strcmp(id,"firewall")){configured=1;reason="Local firewall and Tailnet receive authorization are distinct; authority readiness is not a port grant.";}
        else if(!strcmp(id,"wol")){configured=wol_count()>0;running=0;reason="Saved devices; sending a magic packet never proves device power state.";}
        else if(!strcmp(id,"smart-recovery")){hardware=psram>0;configured=wol_count()>0;running=recovery_active;experimental=true;reason="Bounded optional job; host/service observations are reported separately.";}
        else if(!strcmp(id,"health")){hardware=psram>0;configured=settings.monitoring||health_monitor_enabled();running=configured&&worker_running;experimental=true;reason="Optional worker state; each check has independent evidence and backoff.";}
        else if(!strcmp(id,"resource-guard")){configured=settings.guard;running=configured;experimental=true;reason="Engineering thresholds, not hardware-calibrated limits or socket reservations.";}
        else if(!strcmp(id,"mqtt")){configured=mqtt.enabled;running=mqtt_integration_connected();reason="Observed broker connection; no Home Assistant delivery confirmation.";}
        else if(!strcmp(id,"home-assistant")){configured=mqtt.enabled&&mqtt.home_assistant_discovery;reason="Discovery intent; broker delivery and HA entity creation are not acknowledged here.";}
        else if(!strcmp(id,"ntfy")){configured=ntfy.enabled;reason="Configuration only; last publish does not establish persistent availability.";}
        else if(!strcmp(id,"snmp")){configured=snmp_agent_is_enabled();running=snmp_agent_is_running();reason="Read-only local agent runtime.";}
        else if(!strcmp(id,"ota")){configured=1;reason="Manual OTA support; automated checks/install remain explicit opt-in; no publisher-signing claim.";}
        else if(!strcmp(id,"diagnostic-export")){configured=1;reason="Local on-request allowlisted operational subset; never uploaded automatically.";}
        else if(!strcmp(id,"web-ui")){configured=1;reason="Compiled administration UI; session/access checks remain independent.";}
        else if(!strcmp(id,"destination-test")){hardware=psram>0;configured=1;experimental=true;reason="On-request TCP handshake from this gateway; not application, UDP or LAN-client verification.";}
        else if(!strcmp(id,"service-watch")){hardware=psram>0;configured=watch.enabled;running=watch.enabled&&worker_running;experimental=true;reason="Periodic destination tests of enabled TCP rules; notifies, never changes rules.";}
        else if(!strcmp(id,"profiles")){configured=profile!=PROFILE_NONE;reason="Enable-only presets with token-bound preview and one rollback level.";}
        if(!capability_add(arr,id,compiled,hardware,configured,running,experimental,reason)){cJSON_Delete(root);return NULL;}
    }
    ok=cJSON_AddBoolToObject(root,"authority_ready",policy.authority_ready)
        &&cJSON_AddStringToObject(root,"ethernet",ETH_MANIFEST_SUMMARY)
        &&cJSON_AddStringToObject(root,"tunnel_fragments","bounded-4096B-RX-and-successful-TX-TCP-UDP-IPv6-padding-preheaders")
        &&cJSON_AddStringToObject(root,"hostname_checks","IPv4-DNS-and-Tailnet-cache");
    if(!ok){cJSON_Delete(root);return NULL;}
    return root;
}
