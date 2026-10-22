"""Actual-C passive forwarding diagnostics and transactional WoL regressions.

Synthetic NVS/netif/HTTP only; no device or network traffic. GATEWAY_SANITIZE=1
enables ASan/UBSan on supported hosts. Does not test flash power-loss behavior.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2] + '\n'


def run(program, *, cjson=False):
    with tempfile.TemporaryDirectory(prefix='gateway-ops-') as directory:
        path = Path(directory)
        (path / 'lwip').mkdir()
        for name in ('esp_err.h', 'lwip/pbuf.h', 'lwip/netif.h'):
            (path / name).write_text('/* test definitions precede includes */\n', encoding='utf-8')
        source = path / 'test.c'
        source.write_text(program, encoding='utf-8')
        binary = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=c11', '-pthread', '-Wall', '-Wextra', '-Werror',
                 '-I', str(path), '-I', str(ROOT / 'main'), '-I', str(ROOT / 'external/microlink/components/microlink/include')]
        libs = ['-lws2_32'] if os.name == 'nt' else []
        if cjson:
            dependency = os.environ.get('CJSON_SOURCE')
            if dependency:
                flags += ['-I', str(Path(dependency).parent), dependency]
            else:
                flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
                libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
        if os.environ.get('GATEWAY_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g']
            if os.environ.get('GATEWAY_SANITIZER_NO_PIE') == '1' and os.name != 'nt':
                # Host test executable only. Older ASan can collide with high
                # ASLR entropy on WSL2 even for an empty main (#1614).
                # Keep all sanitizer checks; never alter host ASLR or firmware.
                flags += ['-fno-pie', '-no-pie']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(source), '-o', str(binary), *libs], check=True)
        # A broken sanitizer runtime can recursively print signal reports.
        # Keep diagnostics bounded without hiding its failure/timeout.
        with (path / 'run.log').open('w+b') as log:
            error = None
            try:
                subprocess.run([str(binary)], check=True, timeout=45, stdout=log, stderr=subprocess.STDOUT)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as caught:
                error = caught
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 8192))
            print(log.read().decode('utf-8', errors='replace'), end='', flush=True)
            if error:
                raise error


HEAD = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
typedef int esp_err_t;
struct pbuf;
struct netif;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_NOT_FOUND -3
#define ESP_ERR_INVALID_STATE -4
'''

wol = (ROOT / 'main/wol.c').read_text(encoding='utf-8').split('static bool derive_sta_broadcast', 1)[0]
wol = '\n'.join(line for line in wol.splitlines() if not line.startswith('#include'))
run(HEAD + r'''
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#endif
#include "wol.h"
_Static_assert(sizeof(wol_device_t)==60,"Legacy NVS layout changed");
#define NVS_NAMESPACE "fixture"
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define portMAX_DELAY 0
typedef pthread_mutex_t StaticSemaphore_t;
typedef StaticSemaphore_t *SemaphoreHandle_t;
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(m) assert(!pthread_mutex_lock(m))
#define portEXIT_CRITICAL(m) assert(!pthread_mutex_unlock(m))
static SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *m){assert(!pthread_mutex_init(m,NULL));return m;}
static void xSemaphoreTake(SemaphoreHandle_t m,int wait){(void)wait;assert(!pthread_mutex_lock(m));}
static void xSemaphoreGive(SemaphoreHandle_t m){assert(!pthread_mutex_unlock(m));}
static const char *esp_err_to_name(int err){(void)err;return "fixture failure";}
static void log_stub(const char *tag,const char *format,...){(void)tag;(void)format;}
#define ESP_LOGI(...) log_stub(__VA_ARGS__)
#define ESP_LOGE(...) log_stub(__VA_ARGS__)
typedef unsigned nvs_handle_t;
static wol_device_t disk[WOL_MAX_DEVICES], pending[WOL_MAX_DEVICES];
static int fault, read_fault;
static unsigned writes, commits;
static int nvs_open(const char *ns,int mode,nvs_handle_t *h){assert(!strcmp(ns,NVS_NAMESPACE));*h=1;return mode==NVS_READWRITE&&fault==1?ESP_FAIL:ESP_OK;}
static int nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *n){
 assert(h==1&&!strcmp(key,"wol_devices")&&*n==sizeof disk);memcpy(out,disk,sizeof disk);
 if(read_fault==1)return ESP_FAIL;
 if(read_fault==2)*n=sizeof disk-1;
 return ESP_OK;
}
static int nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t n){
 assert(h==1&&!strcmp(key,"wol_devices")&&n==sizeof disk);writes++;
 if(fault==2)return ESP_FAIL;
 memcpy(pending,data,n);return ESP_OK;
}
static int nvs_commit(nvs_handle_t h){assert(h==1);commits++;if(fault==3)return ESP_FAIL;memcpy(disk,pending,sizeof disk);return ESP_OK;}
static void nvs_close(nvs_handle_t h){assert(h==1);}
''' + wol + r'''
static wol_device_t target(unsigned id){
 wol_device_t d={.mac={2,0,0,0,0,1},.valid=1};d.mac[5]=(uint8_t)id;
 snprintf(d.name,sizeof d.name,"Synthetic target %u",id);strcpy(d.broadcast,"192.0.2.255");return d;
}
static void *concurrent(void *arg){
 wol_device_t d=target((unsigned)(uintptr_t)arg);
 for(unsigned i=0;i<150;i++){assert(wol_set_all(&d,1)==ESP_OK);assert(wol_count()==1);wol_device_t got;assert(wol_get(0,&got));assert(got.valid&&got.port==9&&got.mac[0]==2);}
 return NULL;
}
int main(void){
 uint8_t parsed[6];assert(wol_parse_mac(" 02:AA:00:00:00:01\t",parsed)&&parsed[0]==2&&parsed[1]==0xaa);
 assert(wol_parse_mac("02-aa-00-00-00-01",parsed));
 const char *invalid_mac[]={"","0","02:0:00:00:00:01","02:00:00:00:00:-1","02-00:00:00:00:01","02:00:00:00:00:01junk"};
 for(unsigned i=0;i<sizeof invalid_mac/sizeof invalid_mac[0];i++){
  memset(parsed,0x5a,sizeof parsed);assert(!wol_parse_mac(invalid_mac[i],parsed));for(unsigned b=0;b<6;b++)assert(parsed[b]==0x5a);
 }
 assert(!wol_parse_mac(NULL,parsed)&&!wol_parse_mac("02:00:00:00:00:01",NULL));
 uint32_t rng=1;for(unsigned i=0;i<100000;i++){
  unsigned len=i%49;char *text=malloc(len+1);assert(text);
  for(unsigned j=0;j<len;j++){rng=rng*1664525u+1013904223u;text[j]=(char)(rng>>24);}text[len]=0;
  (void)wol_parse_mac(text,parsed);free(text);
 }
 disk[4]=target(1);wol_init();assert(wol_count()==1);wol_device_t a,b;
 assert(wol_get(0,&a)&&a.port==9);assert(!wol_get(1,&b));
 wol_init();assert(wol_count()==1); /* repeated initialization is not a reload */
 wol_device_t replacement=target(2);
 for(fault=1;fault<=3;fault++){
  assert(wol_set_all(&replacement,1)==ESP_FAIL);assert(wol_count()==1);
  assert(wol_get(0,&b)&&!memcmp(&a,&b,sizeof a));assert(disk[4].mac[5]==1);
 }
 fault=0;assert(wol_set_all(&replacement,1)==ESP_OK);assert(wol_get(0,&b)&&b.mac[5]==2);
 unsigned before=writes;
 assert(wol_set_all(&replacement,-1)==ESP_ERR_INVALID_ARG);
 assert(wol_set_all(&replacement,WOL_MAX_DEVICES+1)==ESP_ERR_INVALID_ARG);
 assert(wol_set_all(NULL,1)==ESP_ERR_INVALID_ARG);
 for(unsigned kind=0;kind<5;kind++){
  wol_device_t bad=target(3);
  if(kind==0)memset(bad.name,'x',sizeof bad.name);
  if(kind==1)memset(bad.broadcast,'x',sizeof bad.broadcast);
  if(kind==2)strcpy(bad.broadcast,"invalid");
  if(kind==3)bad.mac[0]=1;
  if(kind==4)memset(bad.mac,0,6);
  assert(wol_set_all(&bad,1)==ESP_ERR_INVALID_ARG);
 }
 wol_device_t duplicate[2]={replacement,replacement};assert(wol_set_all(duplicate,2)==ESP_ERR_INVALID_ARG);
 assert(writes==before&&wol_get(0,&b)&&b.mac[5]==2);
 s_loaded=false;wol_init();assert(wol_count()==1&&wol_get(0,&b)&&b.mac[5]==2);
 for(read_fault=1;read_fault<=2;read_fault++){s_loaded=false;wol_init();assert(wol_count()==0);}
 read_fault=0;disk[0].mac[0]=1;s_loaded=false;wol_init();assert(wol_count()==0);
 assert(wol_set_all(NULL,0)==ESP_OK&&wol_count()==0);
 pthread_t threads[4];for(unsigned i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,concurrent,(void*)(uintptr_t)(i+1)));
 for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
 puts("PASS: actual WoL layout, sparse legacy load, strict validation, all persistence failures, reload/partial/corrupt records and 600 concurrent save/read cycles");
}
''')

web = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
handler = function(web, 'static const char *rule_peer_path(') + function(web, 'static bool json_age(') + function(web, 'static esp_err_t tailnet_forward_handler(')
run(HEAD + r'''
#include "cJSON.h"
#include "json_guard.h"
#include "tailnet_forward.h"
#include "service_diagnostics.h"
#include "service_check.h"
#include "service_evidence.h"
typedef struct {int status;char *response;} httpd_req_t;
static int64_t fixture_us=100000000; /* uptime 100 s -> now_s 101 */
struct microlink_s {int unused;};static struct microlink_s fixture_ml;static bool peer_online=true,peer_direct=false;static uint32_t peer_ip=0x64400002;
typedef struct {uint32_t vpn_ip;bool online,direct_path;} microlink_peer_info_t;
static struct microlink_s *tailscale_get_microlink(void){return &fixture_ml;}
static int microlink_get_peer_count(struct microlink_s *m){assert(m);return 2;}
static int microlink_get_peer_info(struct microlink_s *m,int i,microlink_peer_info_t *o){assert(m);if(i==1)return -1;*o=(microlink_peer_info_t){.vpn_ip=peer_ip,.online=peer_online,.direct_path=peer_direct};return ESP_OK;}
static int64_t esp_timer_get_time(void){return fixture_us;}
static bool reply_seen;static uint32_t reply_ms;static uint8_t reply_ip[4];static uint16_t reply_port;
bool ml_policy_reply_age(uint8_t proto,const uint8_t ip[4],uint16_t port,uint32_t *age){assert(proto==6||proto==17);memcpy(reply_ip,ip,4);reply_port=port;if(reply_seen)*age=reply_ms;return reply_seen;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){return r->destination_port*7u+1u;}
static bool check_seen;static service_check_result_t check_result;
bool service_check_get(int i,uint32_t token,service_check_result_t *out){(void)i;assert(token);if(!check_seen)return false;*out=check_result;return true;}
const char *service_check_state_name(unsigned s){return s==SC_REACHABLE?"reachable":"not_tested";}
const char *service_check_summary(unsigned s){(void)s;return "fixture summary";}
const char *service_check_next_step(unsigned s){(void)s;return "fixture step";}
#define IPSTR "%u.%u.%u.%u"
#define IP2STR(a) 192u,0u,2u,20u
typedef int esp_netif_t;
typedef struct {struct {uint32_t addr;} ip;} esp_netif_ip_info_t;
static bool authenticated=true,uplink=true,control=true;
static int rows=1,send_result;
static tailnet_forward_rule_t rule={.valid=1,.enabled=1,.proto=6,.source_prefix=32,.listen_port=18830,.destination_port=1883,.destination="100.64.0.2",.name="Synthetic broker"};
static tailnet_forward_runtime_t runtime={.installed=true,.resolved_ip=0x64400002,.accepted_packets=4,.blocked_packets=1};
static int require_auth(httpd_req_t *r){if(authenticated)return ESP_OK;r->status=401;return ESP_FAIL;}
static int httpd_resp_send_500(httpd_req_t *r){r->status=500;return ESP_OK;}
static int httpd_resp_set_type(httpd_req_t *r,const char *type){(void)r;assert(!strcmp(type,"application/json"));return ESP_OK;}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *name,const char *value){(void)r;assert(!strcmp(name,"Cache-Control")&&!strcmp(value,"no-store"));return ESP_OK;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *body){r->response=malloc(strlen(body)+1);assert(r->response);strcpy(r->response,body);return send_result;}
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key){static int netif;assert(!strcmp(key,"WIFI_STA_DEF"));return &netif;}
/* Ethernet disabled: the service listener follows the WiFi STA as before. */
static esp_netif_t *eth_uplink_service_netif(void) { return esp_netif_get_handle_from_ifkey("WIFI_STA_DEF"); }
static int esp_netif_get_ip_info(esp_netif_t *n,esp_netif_ip_info_t *ip){assert(n);ip->ip.addr=uplink?1:0;return ESP_OK;}
static bool tailscale_is_connected(void){return control;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){if(i>=rows)return false;*r=rule;*rt=runtime;return true;}
void tailnet_forward_format_cidr(uint32_t n,uint8_t p,char *out,size_t cap){(void)n;snprintf(out,cap,"192.0.2.42/%u",p);}
''' + handler + r'''
static void check(const char *code){
 httpd_req_t r={.status=200};assert(tailnet_forward_handler(&r)==send_result&&r.status==200);
 cJSON *root=cJSON_Parse(r.response);assert(root);free(r.response);
 cJSON *a=cJSON_GetObjectItem(root,"rules");assert(cJSON_GetArraySize(a)==rows);
 cJSON *j=cJSON_GetArrayItem(a,0),*d=cJSON_GetObjectItem(j,"diagnostic");
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(d,"code")),code));
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(d,"service_status")),service_check_state_name(check_seen?check_result.state:0)));
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(d,"data_plane_status")),"not_verified"));
 cJSON_Delete(root);
}
static cJSON *first_rule(void){
 httpd_req_t r={.status=200};assert(tailnet_forward_handler(&r)==0);cJSON *root=cJSON_Parse(r.response);assert(root);free(r.response);return root;
}
static unsigned allocations,fail_at;
static void *allocate(size_t n){return ++allocations==fail_at?NULL:malloc(n);}
int main(void){
 check("mapping_installed");
 for(unsigned mask=0;mask<64;mask++){
  rule.enabled=!!(mask&1);uplink=!!(mask&2);control=!!(mask&4);runtime.resolved_ip=(mask&8)?1:0;
  runtime.installed=!!(mask&16);runtime.error[0]=(mask&32)?'x':0;
  const char *expected=!(mask&1)?"disabled":!(mask&2)?"uplink_no_ipv4":!(mask&4)?"control_not_ready":
      !(mask&8)?"destination_unresolved":!(mask&16)?"mapping_not_installed":(mask&32)?"runtime_error":"mapping_installed";
  check(expected);
 }
 rule.enabled=uplink=control=true;runtime.resolved_ip=1;runtime.installed=true;runtime.error[0]=0;
 rows=TAILNET_FORWARD_MAX;check("mapping_installed");
 httpd_req_t size={.status=200};assert(tailnet_forward_handler(&size)==0);printf("PASS: maximum diagnostic response %zu bytes; no probe/task/socket API in handler\n",strlen(size.response));free(size.response);
 memset(rule.name,1,sizeof rule.name-1);rule.name[sizeof rule.name-1]=0;
 memset(rule.destination,'a',sizeof rule.destination-1);rule.destination[sizeof rule.destination-1]=0;
 memset(runtime.error,2,sizeof runtime.error-1);runtime.error[sizeof runtime.error-1]=0;
 rule.listen_port=rule.destination_port=65535;runtime.accepted_packets=runtime.blocked_packets=UINT32_MAX;
 httpd_req_t worst={.status=200};assert(tailnet_forward_handler(&worst)==0);
 assert(strlen(worst.response)<16384);printf("PASS: bounded escaped eight-rule diagnostic response %zu bytes\n",strlen(worst.response));free(worst.response);
 runtime.error[0]=0;
 authenticated=false;httpd_req_t denied={.status=200};assert(tailnet_forward_handler(&denied)==ESP_FAIL&&denied.status==401&&!denied.response);authenticated=true;
 send_result=-9;check("mapping_installed");send_result=0;
 /* Activity ages, null when never; reply evidence keyed by resolved IP/port; check result shape. */
 rows=1;runtime.resolved_ip=0x64400002;rule.destination_port=1883;runtime.last_accepted_s=0;runtime.last_blocked_s=91;
 cJSON *root=first_rule(),*j=cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0),*act=cJSON_GetObjectItem(j,"activity");
 assert(cJSON_IsNull(cJSON_GetObjectItem(act,"last_accepted_age_s"))&&cJSON_GetObjectItem(act,"last_rejected_age_s")->valuedouble==10);
 assert(cJSON_IsNull(cJSON_GetObjectItem(act,"service_reply_age_s"))&&!cJSON_GetObjectItem(j,"destination_check"));
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(act,"peer_path")),"relay"));cJSON_Delete(root);
 peer_direct=true;root=first_rule();assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0),"activity"),"peer_path")),"direct"));cJSON_Delete(root);
 peer_online=false;root=first_rule();assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0),"activity"),"peer_path")),"offline"));cJSON_Delete(root);
 peer_ip=0x64400099;root=first_rule();assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0),"activity"),"peer_path")),"unknown"));cJSON_Delete(root);
 control=false;peer_ip=0x64400002;peer_online=true;root=first_rule();assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0),"activity"),"peer_path")),"unknown"));control=true;cJSON_Delete(root);
 root=first_rule();j=cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0);act=cJSON_GetObjectItem(j,"activity");
 assert(reply_ip[0]==100&&reply_ip[1]==64&&reply_ip[2]==0&&reply_ip[3]==2&&reply_port==1883);
 assert(cJSON_GetObjectItem(j,"rule_token")->valuedouble==1883*7+1&&cJSON_GetObjectItem(j,"index")->valuedouble==0);cJSON_Delete(root);
 reply_seen=true;reply_ms=4999;runtime.last_accepted_s=200; /* clock skew: stamp ahead of now -> 0, never negative */
 check_seen=true;check_result=(service_check_result_t){.state=SC_REACHABLE,.token=1,.latency_ms=42,.resolved_ip=0x64400002,.observed_ms=95000};
 root=first_rule();j=cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0);act=cJSON_GetObjectItem(j,"activity");
 assert(cJSON_GetObjectItem(act,"service_reply_age_s")->valuedouble==4&&cJSON_GetObjectItem(act,"last_accepted_age_s")->valuedouble==0);
 cJSON *dc=cJSON_GetObjectItem(j,"destination_check");
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(dc,"state")),"reachable")&&!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(dc,"checked_ip")),"100.64.0.2"));
 assert(cJSON_GetObjectItem(dc,"latency_ms")->valuedouble==42&&cJSON_GetObjectItem(dc,"age_s")->valuedouble==5);
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(cJSON_GetObjectItem(j,"diagnostic"),"service_status")),"reachable"));
 cJSON_Delete(root);
 /* Evidence refines only the matching passive states. */
 runtime.last_accepted_s=0;runtime.last_blocked_s=0;reply_seen=false;check_seen=false;check("mapping_installed");
 runtime.last_blocked_s=50;check("source_rejected");
 /* A destination test/another rule can share the tuple's reply evidence.
  * It must never hide this binding's rejected-only LAN observations. */
 reply_seen=true;check("source_rejected");
 check_seen=true;check_result.state=SC_REACHABLE;check("source_rejected");
 check_result.state=SC_NO_ANSWER;check("source_rejected");
 reply_seen=false;check_seen=false;runtime.last_accepted_s=60;check("mapping_installed");
 check_seen=true;check_result.state=SC_NO_ANSWER;check("destination_no_answer");
 check_result.state=SC_REACHABLE;check("destination_reachable");
 reply_seen=true;check("service_replied");
 rule.enabled=0;check("ready_to_enable");check_result.state=SC_NO_ANSWER;check("disabled");rule.enabled=1;
 uplink=false;check("uplink_no_ipv4");uplink=true; /* passive faults are never masked by evidence */
 reply_seen=false;check_seen=false;runtime.last_accepted_s=runtime.last_blocked_s=0;
 runtime.resolved_ip=0;root=first_rule();cJSON_Delete(root);
 runtime.resolved_ip=1;reply_seen=false;check_seen=false;
 cJSON_Hooks hooks={allocate,free};cJSON_InitHooks(&hooks);allocations=0;fail_at=0;
 httpd_req_t base={.status=200};assert(tailnet_forward_handler(&base)==0);unsigned count=allocations;free(base.response);
 for(unsigned fail=1;fail<=count;fail++){
  allocations=0;fail_at=fail;httpd_req_t r={.status=200};
  int result=tailnet_forward_handler(&r);
  assert((result==ESP_FAIL&&r.status==500&&!r.response)||(result==0&&r.status==200&&r.response));free(r.response);
 }
 cJSON_InitHooks(NULL);
 puts("PASS: actual diagnostic GET authentication, 64 state combinations, eight-rule bound, send error and every JSON allocation failure");
}
''', cjson=True)

wol_handlers = function(web, 'static esp_err_t wol_save_handler(') + function(web, 'static esp_err_t wol_send_handler(')
run(HEAD + r'''
#include "cJSON.h"
#include "json_guard.h"
#include "wol.h"
#define HTTPD_400_BAD_REQUEST 400
typedef struct {const char *body;int status;char response[256];} httpd_req_t;
static bool authenticated=true;
static unsigned saves,sends,changes;
static int saved_result;
static size_t strlcpy(char *d,const char *s,size_t cap){size_t n=strlen(s);if(cap){size_t k=n<cap-1?n:cap-1;memcpy(d,s,k);d[k]=0;}return n;}
static const char *esp_err_to_name(int err){(void)err;return "fixture";}
static int require_auth(httpd_req_t *r){if(authenticated)return ESP_OK;r->status=401;return ESP_FAIL;}
static int httpd_resp_send_500(httpd_req_t *r){r->status=500;return ESP_OK;}
static int httpd_resp_send_err(httpd_req_t *r,int status,const char *why){r->status=status;strlcpy(r->response,why,sizeof r->response);return ESP_OK;}
static int httpd_resp_set_type(httpd_req_t *r,const char *t){(void)r;assert(!strcmp(t,"application/json"));return ESP_OK;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);return ESP_OK;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){strlcpy(r->response,s,sizeof r->response);return ESP_OK;}
static char *malloc_body_buf(size_t cap){return malloc(cap);}
static int recv_body(httpd_req_t *r,char *out,size_t cap,void *unused){(void)unused;assert(strlen(r->body)<cap);strcpy(out,r->body);return ESP_OK;}
static void mqtt_integration_wol_changed(void){changes++;}
typedef unsigned ip4_addr_t;
static bool ip4addr_aton(const char *text,ip4_addr_t *out){(void)out;return !strcmp(text,"192.0.2.255");}
bool wol_parse_mac(const char *text,uint8_t out[6]){(void)out;return !strcmp(text,"02:00:00:00:00:01");}
esp_err_t wol_set_all(const wol_device_t *d,int n){assert(n>=0&&n<=WOL_MAX_DEVICES);if(n)assert(d[0].port==9);saves++;return saved_result;}
esp_err_t wol_send_index(int i){assert(i>=0&&i<WOL_MAX_DEVICES);sends++;return saved_result;}
esp_err_t wol_send_saved_mac_text(const char *mac){assert(!strcmp(mac,"02:00:00:00:00:01"));sends++;return saved_result;}
''' + wol_handlers + r'''
static httpd_req_t send(const char *body,bool wake){
 httpd_req_t r={body,200,{0}};saves=sends=changes=0;
 if(wake)(void)wol_send_handler(&r);else (void)wol_save_handler(&r);
 return r;
}
int main(void){
 const char *bad[]={"{}","[]","{\"index\":0.5}","{\"index\":-1}","{\"index\":12}","{\"index\":true}","{\"mac\":4}","{\"index\":0,\"mac\":\"02:00:00:00:00:01\"}"};
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++)assert(send(bad[i],true).status==400&&!sends);
 httpd_req_t r=send("{\"index\":0}",true);assert(r.status==200&&sends==1);
 cJSON *reply=cJSON_Parse(r.response);assert(cJSON_IsTrue(cJSON_GetObjectItem(reply,"magic_packet_sent")));
 assert(!strcmp(cJSON_GetStringValue(cJSON_GetObjectItem(reply,"device_state")),"not_verified"));cJSON_Delete(reply);
 const char *fields[]={"\"name\":false","\"name\":\"01234567890123456789012345678901\"","\"broadcast\":5","\"broadcast\":\"0123456789012345\"","\"port\":9.5","\"port\":true","\"port\":0","\"port\":65536"};
 char body[256];
 for(unsigned i=0;i<sizeof fields/sizeof fields[0];i++){
  snprintf(body,sizeof body,"{\"devices\":[{\"mac\":\"02:00:00:00:00:01\",%s}]}",fields[i]);
  assert(send(body,false).status==400&&!saves&&!changes);
 }
 strcpy(body,"{\"devices\":[{\"mac\":\"02:00:00:00:00:01\",\"name\":\"Synthetic NAS\"}]}");
 assert(send(body,false).status==200&&saves==1&&changes==1);
 saved_result=ESP_FAIL;assert(send(body,false).status==500&&saves==1&&!changes);
 saved_result=ESP_ERR_INVALID_ARG;assert(send(body,false).status==400&&saves==1&&!changes);
 saved_result=ESP_ERR_INVALID_ARG;assert(send("{\"index\":0}",true).status==400);
 saved_result=ESP_ERR_NOT_FOUND;assert(send("{\"index\":0}",true).status==404);
 authenticated=false;assert(send(body,false).status==401&&!saves);assert(send("{\"index\":0}",true).status==401&&!sends);
 puts("PASS: actual WoL API auth, field limits/types, fractional/ambiguous indices, save errors and truthful packet-sent/not-verified response");
}
''', cjson=True)
