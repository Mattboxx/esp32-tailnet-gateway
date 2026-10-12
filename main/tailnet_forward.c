#include "tailnet_forward.h"
#include "tailnet_reassembly.h"
#include "control_validation.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/inet.h"
#include "lwip/ip4.h"
#include "lwip/prot/ip.h"
#include "microlink.h"
#include "nvs.h"
#include "nvs_params.h"
#include "portmap.h"
#include "forwarding_config.h"
#include "tailscale_config.h"
#include "netif_hooks.h"
#include "web_ui.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "ap_policy.h"

#define NVS_KEY "tn_fwd"
#define STORE_MAGIC 0x544e4631u

typedef struct { uint32_t magic; tailnet_forward_rule_t rules[TAILNET_FORWARD_MAX]; } store_t;
static tailnet_forward_rule_t s_rules[TAILNET_FORWARD_MAX];
static tailnet_forward_runtime_t s_runtime[TAILNET_FORWARD_MAX];
static int s_count;
static bool s_loaded;
static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static uint64_t s_generation;
typedef struct { bool installed; tailnet_forward_mapping_t mapping; } active_mapping_t;
/* Only the TCP/IP task installs/replaces these snapshots and authorizes
 * packets from them. Configuration/resolution tasks never modify live policy. */
static active_mapping_t s_active[TAILNET_FORWARD_MAX];
#define LOCK() do { if (s_lock) xSemaphoreTake(s_lock, portMAX_DELAY); } while (0)
#define UNLOCK() do { if (s_lock) xSemaphoreGive(s_lock); } while (0)

static bool cgnat(uint32_t hbo) { return (hbo & 0xffc00000u) == 0x64400000u; }
static bool hostname_valid(const char *s) {
    if (!s || !memchr(s, 0, TAILNET_FORWARD_DEST_LEN)) return false;
    size_t n = strlen(s);
    if (!n || n >= TAILNET_FORWARD_DEST_LEN) return false;
    for (size_t i=0;i<n;i++) if (!(isalnum((unsigned char)s[i]) || s[i]=='-' || s[i]=='.')) return false;
    return s[0]!='.' && s[n-1]!='.';
}

static bool rule_is_valid(const tailnet_forward_rule_t *r)
{
    if (r->valid != 1 || r->enabled > 1 || (r->proto != 6 && r->proto != 17) ||
        !r->listen_port || !r->destination_port || r->source_prefix > 32 ||
        !memchr(r->name, 0, sizeof r->name) || !hostname_valid(r->destination)) return false;
    uint32_t mask = r->source_prefix == 0 ? 0 : (r->source_prefix == 32 ? UINT32_MAX : UINT32_MAX << (32 - r->source_prefix));
    /* Stored networks are already normalized by parse_cidr. Do not silently
     * broaden an inconsistent saved policy while loading or accepting it. */
    return (r->source_network & mask) == r->source_network;
}

esp_err_t tailnet_forward_parse_cidr(const char *text, uint32_t *network, uint8_t *prefix) {
    if (!text || !network || !prefix || strlen(text) >= 32) return ESP_ERR_INVALID_ARG;
    char copy[32]; strlcpy(copy,text,sizeof copy); char *slash=strchr(copy,'/');
    if (!slash) return ESP_ERR_INVALID_ARG;
    *slash++=0;
    unsigned p; ip4_addr_t a;
    if (!control_parse_index(slash,33,&p) || !ip4addr_aton(copy,&a)) return ESP_ERR_INVALID_ARG;
    uint32_t h=lwip_ntohl(a.addr), mask=p==0?0:(p==32?0xffffffffu:0xffffffffu<<(32-p));
    *network=h&mask; *prefix=(uint8_t)p; return ESP_OK;
}
void tailnet_forward_format_cidr(uint32_t n,uint8_t p,char *out,size_t z) {
    snprintf(out,z,"%u.%u.%u.%u/%u",(unsigned)(n>>24),(unsigned)((n>>16)&255),(unsigned)((n>>8)&255),(unsigned)(n&255),p);
}

static bool resolve_rule(int i) {
    tailnet_forward_rule_t *r=&s_rules[i]; tailnet_forward_runtime_t *rt=&s_runtime[i];
    uint32_t previous=rt->resolved_ip; bool was_installed=rt->installed;
    rt->error[0]=0;
    if (!r->enabled) { rt->resolved_ip=0;rt->installed=false;strlcpy(rt->error,"disabled",sizeof rt->error);return false; }
    if (!tailscale_connected || !tailscale_get_microlink()) { rt->resolved_ip=0;rt->installed=false;strlcpy(rt->error,"Tailnet offline",sizeof rt->error);return false; }
    ip4_addr_t a; uint32_t h=0;
    if (ip4addr_aton(r->destination,&a)) h=lwip_ntohl(a.addr);
    else { microlink_t *ml=tailscale_get_microlink(); if (!tailscale_connected || !ml) { rt->resolved_ip=0;rt->installed=false;strlcpy(rt->error,"Tailnet offline",sizeof rt->error);return false; } h=microlink_resolve(ml,r->destination); }
    if (!cgnat(h)) { rt->resolved_ip=0;rt->installed=false;strlcpy(rt->error,"not a Tailnet IPv4 address",sizeof rt->error);return false; }
    rt->resolved_ip=h;rt->installed=(previous==h)&&was_installed;return true;
}
static void manager(void *arg) {
    (void)arg;
    int64_t next_refresh = 0;
    for (;;) {
        /* Reuse this task's 4KB stack for allocation/retry bookkeeping.
         * The actual WiFi transition still runs on its separate 8KB stack.
         * Never create/log task failures on the small timer-service stack. */
        ap_policy_poll();
        int64_t now = esp_timer_get_time();
        if (now < next_refresh) { vTaskDelay(pdMS_TO_TICKS(100)); continue; }
        next_refresh = now + 3000000;
        bool changed=false;
        LOCK();
        for(int i=0;i<s_count;i++){uint32_t old=s_runtime[i].resolved_ip;resolve_rule(i);if(old!=s_runtime[i].resolved_ip)changed=true;}
        UNLOCK();
        netif_hooks_refresh();
        tailnet_reassembly_refresh();
        if(changed)portmap_install_all();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
void tailnet_forward_init(void) {
    if(s_loaded)return;
    if(!s_lock)s_lock=xSemaphoreCreateMutexStatic(&s_lock_storage);
    memset(s_rules,0,sizeof s_rules);memset(s_runtime,0,sizeof s_runtime);
    memset(s_active,0,sizeof s_active);s_generation++;
    s_count=0;
    store_t st={0};size_t len=sizeof st;nvs_handle_t nvs;
    if(nvs_open(NVS_NAMESPACE,NVS_READONLY,&nvs)==ESP_OK){
        if(nvs_get_blob(nvs,NVS_KEY,&st,&len)==ESP_OK&&len==sizeof st&&st.magic==STORE_MAGIC){
            bool valid=true;
            for(int i=0;i<TAILNET_FORWARD_MAX;i++){
                const tailnet_forward_rule_t *r=&st.rules[i];
                if(!r->valid)continue;
                ip4_addr_t a;
                if(!rule_is_valid(r)||(ip4addr_aton(r->destination,&a)&&!cgnat(lwip_ntohl(a.addr)))){valid=false;break;}
                for(int j=0;j<s_count;j++)
                    if(r->enabled&&s_rules[j].enabled&&r->proto==s_rules[j].proto&&r->listen_port==s_rules[j].listen_port){valid=false;break;}
                if(!valid)break;
                /* Compact occupied slots: runtime/getters iterate 0..count. */
                s_rules[s_count++]=*r;
            }
            if(!valid){
                memset(s_rules,0,sizeof s_rules);s_count=0;
                ESP_LOGE("tn_forward","Invalid stored forwarding rules; ignoring the whole table");
            }
        }
        nvs_close(nvs);
    }
    s_loaded=true;
    if(xTaskCreate(manager,"tn_forward",4096,NULL,4,NULL)!=pdPASS)
        ESP_LOGE("tn_forward","Forwarding manager could not start");
}
int tailnet_forward_count(void){if(!s_loaded)tailnet_forward_init();LOCK();int n=s_count;UNLOCK();return n;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){if(!s_loaded)tailnet_forward_init();LOCK();bool ok=i>=0&&i<s_count&&s_rules[i].valid;if(ok){if(r)*r=s_rules[i];if(rt)*rt=s_runtime[i];}UNLOCK();return ok;}
static esp_err_t set_all_locked(const tailnet_forward_rule_t *rules,int count,char *error,size_t en);
bool tailnet_forward_listen_conflicts(uint8_t proto,uint16_t port){LOCK();bool found=false;for(int i=0;i<s_count;i++)if(s_rules[i].valid&&s_rules[i].enabled&&s_rules[i].proto==proto&&s_rules[i].listen_port==port){found=true;break;}UNLOCK();return found;}

esp_err_t tailnet_forward_set_all(const tailnet_forward_rule_t *rules,int count,char *error,size_t en) {
    forwarding_config_lock();
    esp_err_t err=set_all_locked(rules,count,error,en);
    forwarding_config_unlock();
    if(err==ESP_OK)portmap_install_all();
    return err;
}
static esp_err_t set_all_locked(const tailnet_forward_rule_t *rules,int count,char *error,size_t en) {
    if(!rules||count<0||count>TAILNET_FORWARD_MAX)return ESP_ERR_INVALID_ARG;
    for(int i=0;i<count;i++){
        const tailnet_forward_rule_t *r=&rules[i];
        if(!rule_is_valid(r)){if(error)snprintf(error,en,"Invalid rule %d",i+1);return ESP_ERR_INVALID_ARG;}
        ip4_addr_t a;if(ip4addr_aton(r->destination,&a)&&!cgnat(lwip_ntohl(a.addr))){if(error)snprintf(error,en,"Rule %d destination must be in 100.64.0.0/10",i+1);return ESP_ERR_INVALID_ARG;}
        for(int j=0;j<i;j++)if(rules[j].enabled&&r->enabled&&rules[j].proto==r->proto&&rules[j].listen_port==r->listen_port){if(error)snprintf(error,en,"Duplicate listen port in rule %d",i+1);return ESP_ERR_INVALID_STATE;}
        if(r->enabled&&portmap_listen_conflicts(r->proto,r->listen_port)){if(error)snprintf(error,en,"Rule %d conflicts with AP-side forwarding",i+1);return ESP_ERR_INVALID_STATE;}
        if(r->enabled&&r->proto==TAILNET_FORWARD_PROTO_TCP&&web_ui_port_reserved(r->listen_port)){if(error)snprintf(error,en,"Rule %d conflicts with the Web UI port",i+1);return ESP_ERR_INVALID_STATE;}
        if(r->enabled&&r->proto==TAILNET_FORWARD_PROTO_TCP&&tailscale_exit_server_active()&&r->listen_port==tailscale_peerapi_port()){if(error)snprintf(error,en,"Rule %d conflicts with the exit-node DNS port",i+1);return ESP_ERR_INVALID_STATE;}
    }
    store_t st={.magic=STORE_MAGIC};memcpy(st.rules,rules,count*sizeof rules[0]);nvs_handle_t nvs;esp_err_t err=nvs_open(NVS_NAMESPACE,NVS_READWRITE,&nvs);
    if(err==ESP_OK){err=nvs_set_blob(nvs,NVS_KEY,&st,sizeof st);if(err==ESP_OK)err=nvs_commit(nvs);nvs_close(nvs);}if(err!=ESP_OK)return err;
    LOCK();
    memset(s_rules,0,sizeof s_rules);memset(s_runtime,0,sizeof s_runtime);memcpy(s_rules,rules,count*sizeof rules[0]);s_count=count;
    s_generation++;
    for(int i=0;i<count;i++)resolve_rule(i);
    UNLOCK();
    return ESP_OK;
}
esp_err_t tailnet_forward_set_enabled(int i,bool enabled)
{
    tailnet_forward_rule_t copy[TAILNET_FORWARD_MAX];
    forwarding_config_lock();
    LOCK();
    if(i<0||i>=s_count){UNLOCK();forwarding_config_unlock();return ESP_ERR_INVALID_ARG;}
    int count=s_count;memcpy(copy,s_rules,sizeof copy);
    UNLOCK();
    copy[i].enabled=enabled;char e[64];
    esp_err_t err=set_all_locked(copy,count,e,sizeof e);
    forwarding_config_unlock();
    if(err==ESP_OK)portmap_install_all();
    return err;
}
bool tailnet_forward_get_mapping(int i,uint8_t *proto,uint16_t *listen,uint32_t *dest,uint16_t *dport){LOCK();bool ok=i>=0&&i<s_count&&s_rules[i].valid&&s_rules[i].enabled&&s_runtime[i].resolved_ip;if(ok){*proto=s_rules[i].proto;*listen=s_rules[i].listen_port;*dest=lwip_htonl(s_runtime[i].resolved_ip);*dport=s_rules[i].destination_port;}UNLOCK();return ok;}
int tailnet_forward_snapshot_mappings(tailnet_forward_mapping_t *out, int capacity)
{
    if(!out||capacity<=0)return 0;
    LOCK();int count=0;
    for(int i=0;i<s_count&&count<capacity;i++) {
        if(!s_rules[i].valid||!s_rules[i].enabled||!s_runtime[i].resolved_ip)continue;
        out[count++]=(tailnet_forward_mapping_t){.rule=s_rules[i],.destination_nbo=lwip_htonl(s_runtime[i].resolved_ip),.slot=i,.generation=s_generation};
    }
    UNLOCK();return count;
}
void tailnet_forward_prepare_install(void)
{
    LOCK();memset(s_active,0,sizeof s_active);
    for(int i=0;i<s_count;i++)s_runtime[i].installed=false;
    UNLOCK();
}
void tailnet_forward_mark_installed(const tailnet_forward_mapping_t *mapping,bool ok,const char *err)
{
    if(!mapping||mapping->slot<0||mapping->slot>=TAILNET_FORWARD_MAX)return;
    int i=mapping->slot;
    LOCK();
    s_active[i].installed=ok;
    if(ok)s_active[i].mapping=*mapping;
    /* Do not report an old callback's binding as the newly saved rule. */
    if(i<s_count&&mapping->generation==s_generation&&mapping->destination_nbo==lwip_htonl(s_runtime[i].resolved_ip)) {
        s_runtime[i].installed=ok;
        if(err)strlcpy(s_runtime[i].error,err,sizeof s_runtime[i].error);
        else if(ok)s_runtime[i].error[0]=0;
    }
    UNLOCK();
}

static bool packet_fields(struct pbuf *p, bool eth, uint32_t *src,
                          uint32_t *destination_nbo, uint8_t *proto, uint16_t *dport)
{
    /* Inspect bounded copies, not potentially unaligned/incomplete headers
     * in the first pbuf. A split header must not bypass the source policy. */
    uint16_t off = eth ? 14 : 0;
    uint8_t ip[20], ports[4], type[2];
    if (!p) return false;
    if (eth && (pbuf_copy_partial(p, type, sizeof type, 12) != sizeof type ||
                type[0] != 8 || type[1] != 0)) return false;
    if (pbuf_copy_partial(p, ip, sizeof ip, off) != sizeof ip || (ip[0] >> 4) != 4) return false;
    uint16_t ihl = (ip[0] & 15) * 4;
    uint16_t total = ((uint16_t)ip[2] << 8) | ip[3];
    uint16_t fragment = ((uint16_t)ip[6] << 8) | ip[7];
    if (ihl < 20 || total < ihl + sizeof ports || (fragment & IP_OFFMASK)) return false;
    *proto = ip[9];
    if (*proto != 6 && *proto != 17) return false;
    if (pbuf_copy_partial(p, ports, sizeof ports, off + ihl) != sizeof ports) return false;
    *dport = ((uint16_t)ports[2] << 8) | ports[3];
    uint32_t source_nbo;
    memcpy(&source_nbo, ip + 12, sizeof source_nbo);
    memcpy(destination_nbo, ip + 16, sizeof *destination_nbo);
    *src = lwip_ntohl(source_nbo);
    return true;
}
static bool allow_packet(struct pbuf *p, bool eth, uint32_t local_ip_nbo, bool uplink)
{
    uint32_t src, destination; uint8_t proto; uint16_t dp;
    /* Match the pinned SDK's ip4_input DNAT condition: destination equals
     * the receiving interface address. Routed traffic is not this listener. */
    if (!local_ip_nbo || !packet_fields(p, eth, &src, &destination, &proto, &dp) || destination != local_ip_nbo) return true;
    LOCK();
    for (int i = 0; i < TAILNET_FORWARD_MAX; i++) {
        const tailnet_forward_mapping_t *m=&s_active[i].mapping;
        const tailnet_forward_rule_t *r=&m->rule;
        if (!s_active[i].installed || r->proto != proto || r->listen_port != dp) continue;
        bool ok = false;
        if (r->source_prefix <= 32) {
            uint32_t mask = r->source_prefix == 0 ? 0 : (r->source_prefix == 32 ? UINT32_MAX : UINT32_MAX << (32 - r->source_prefix));
            ok = uplink && local_ip_nbo==m->binding_ip_nbo && ((src & mask) == r->source_network);
        }
        if(i<s_count&&m->generation==s_generation) {
            if (ok) s_runtime[i].accepted_packets++; else s_runtime[i].blocked_packets++;
        }
        UNLOCK();
        return ok;
    }
    UNLOCK();
    return true;
}
bool tailnet_forward_allow_uplink_packet(struct pbuf *p, uint32_t local_ip_nbo)
{
    return allow_packet(p,true,local_ip_nbo,true);
}
bool tailnet_forward_allow_non_uplink_packet(struct pbuf *p, bool eth, uint32_t local_ip_nbo)
{
    return allow_packet(p,eth,local_ip_nbo,false);
}
bool tailnet_forward_allow_ipv4_packet(struct pbuf *p,struct netif *input)
{
    /* Match receive-DNAT eligibility at the point the SDK consumes input,
     * not the earlier Wi-Fi/WireGuard callback that merely queues it.
     * NAPT-enabled AP input is not DNAT: preserve its local DNS/services. */
    if(!input||input->napt)return true;
    bool uplink=input->name[0]=='s'&&input->name[1]=='t';
    return allow_packet(p,false,netif_ip4_addr(input)->addr,uplink);
}
bool tailnet_forward_is_routed_target(uint8_t proto,uint32_t dst,uint16_t port){LOCK();bool found=false;for(int i=0;i<TAILNET_FORWARD_MAX;i++)if(s_active[i].installed&&s_active[i].mapping.rule.proto==proto&&s_active[i].mapping.destination_nbo==dst&&s_active[i].mapping.rule.destination_port==port){found=true;break;}UNLOCK();return found;}
bool tailnet_forward_is_routed_response(uint8_t proto,uint32_t src,uint16_t port){return tailnet_forward_is_routed_target(proto,src,port);}
void tailnet_forward_totals(uint32_t *enabled,uint32_t *installed,uint32_t *accepted,uint32_t *blocked){uint32_t e=0,n=0,a=0,b=0;LOCK();for(int i=0;i<s_count;i++){if(s_rules[i].enabled)e++;if(s_runtime[i].installed)n++;a+=s_runtime[i].accepted_packets;b+=s_runtime[i].blocked_packets;}UNLOCK();if(enabled)*enabled=e;if(installed)*installed=n;if(accepted)*accepted=a;if(blocked)*blocked=b;}
