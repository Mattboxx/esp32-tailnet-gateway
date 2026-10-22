"""Actual operational POST parser/auth dispatch, synthetic HTTP/module sinks.
Does not prove the session implementation, worker scheduling or physical NVS.
"""
from pathlib import Path
import os
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/homelab_ops_http.c').read_text(encoding='utf-8')
header=(ROOT/'main/homelab_ops.h').read_text(encoding='utf-8')
wol=(ROOT/'main/wol.h').read_text(encoding='utf-8')
wolsource=(ROOT/'main/wol.c').read_text(encoding='utf-8')
def function(text,signature):
    at=text.index(signature);return text[at:text.index('\n}',at)+2]+'\n'
types=header[header.index('typedef struct'):header.index('void homelab_ops_init')]
health=(ROOT/'main/health_monitor.h').read_text(encoding='utf-8')
types+=health[health.index('typedef struct'):health.index('void health_monitor_init')]
woltype=wol[wol.index('typedef struct'):wol.index('void      wol_init')]
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "cJSON.h"
#include "json_guard.h"
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#define ESP_ERR_NO_MEM -4
#define MALLOC_CAP_SPIRAM 0
#define MALLOC_CAP_8BIT 0
#define HTTPD_400_BAD_REQUEST 400
#define WOL_MAX_DEVICES 12
#define TAILNET_FORWARD_MAX 8
#define CONFIG_LWIP_MAX_SOCKETS 31
typedef int esp_err_t;
typedef struct {int content_len,offset,status;const char *body;bool authorized;} httpd_req_t;
static unsigned mutations,auth_calls;
static int module_error,heap_fail;
static int web_ui_require_auth(httpd_req_t *r){auth_calls++;return r->authorized?ESP_OK:ESP_FAIL;}
static void httpd_resp_send_err(httpd_req_t *r,int status,const char *s){r->status=status;(void)s;}
static void httpd_resp_send_500(httpd_req_t *r){r->status=500;}
static void httpd_resp_send_408(httpd_req_t *r){r->status=408;}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;}
static void httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){(void)r;(void)k;(void)v;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){assert(s);(void)r;return ESP_OK;}
static int httpd_req_recv(httpd_req_t *r,char *out,int n){memcpy(out,r->body+r->offset,n);r->offset+=n;return n;}
static void *heap_caps_calloc(size_t a,size_t b,int caps){(void)caps;return heap_fail?NULL:calloc(a,b);}
static const char *esp_err_to_name(int e){(void)e;return "fixture-error";}
'''
adapters=r'''
static bool wol_get(int index,wol_device_t *d){if(index)return false;memset(d,0,sizeof *d);d->mac[0]=2;d->mac[5]=1;return true;}
static int homelab_ops_cancel(void){mutations++;return module_error;}
static int homelab_ops_request(int i,bool wake,bool remote){assert(!i&&!remote);(void)wake;mutations++;return module_error;}
static int homelab_ops_set_settings(const ops_settings_t *s){assert(s);mutations++;return module_error;}
static int health_monitor_set(const health_config_t *c){assert(c);mutations++;return module_error;}
static int homelab_ops_set_device(int i,const ops_device_t *p){assert(!i&&p&&p->mac[0]==2);mutations++;return module_error;}
static int service_lease_set_mode(int i,uint32_t token,uint32_t seconds,bool permanent,bool remove){assert(!i&&token==123&&seconds==60&&!permanent);(void)remove;mutations++;return module_error;}
static void portmap_install_all(void){}
'''
tests=r'''
static int call(const char *body,bool auth){httpd_req_t r={.body=body,.content_len=(int)strlen(body),.authorized=auth,.status=200};(void)post_ops(&r);return r.status;}
int main(void){
    const char *recover="{\"action\":\"recover\",\"index\":0,\"mac\":\"02:00:00:00:00:01\"}";
    call(recover,false);assert(auth_calls==1&&!mutations);
    assert(call(recover,true)==200 && mutations==1);
    const char *bad[]={"[]","{\"action\":\"cancel\",\"action\":\"recover\"}",
        "{\"action\":\"recover\",\"index\":0.5,\"mac\":\"02:00:00:00:00:01\"}",
        "{\"action\":\"recover\",\"index\":0,\"mac\":\"02:00:00:00:00:02\"}",
        "{\"action\":\"settings\",\"monitoring\":\"false\"}",
        "{\"action\":\"health\",\"enabled\":true,\"notify\":false,\"interval_s\":30.5}",
        "{\"action\":\"lease\",\"index\":0,\"rule_token\":123.5,\"seconds\":60,\"permanent\":false}",
        "{\"action\":\"cancel\"} trailing"};
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++){assert(call(bad[i],true)==400);assert(mutations==1);}
    module_error=ESP_ERR_INVALID_STATE;assert(call(recover,true)==409);
    module_error=ESP_ERR_NO_MEM;assert(call(recover,true)==503);
    module_error=-99;assert(call(recover,true)==500);module_error=0;
    unsigned before=mutations;heap_fail=1;assert(call(recover,true)==500 && mutations==before);heap_fail=0;
    assert(call("{\"action\":\"lease\",\"index\":0,\"rule_token\":123,\"seconds\":60,\"permanent\":false}",true)==200);
    assert(call("{\"action\":\"health\",\"enabled\":false,\"notify\":false,\"interval_s\":60,\"failure_threshold\":3,\"gateway_port\":0,\"dns_name\":\"\",\"internet_ip\":\"\",\"internet_port\":0,\"tailnet_target\":\"\",\"tailnet_port\":0}",true)==200);
    assert(call("{\"action\":\"settings\",\"monitoring\":false,\"guard\":false,\"remote_commands\":false,\"interval_s\":60,\"minimum_internal\":16384,\"minimum_largest\":8192,\"socket_reserve\":4}",true)==200);
    puts("PASS: actual operational API MAC binding, auth dispatch, duplicate/type/fraction/trailing rejection, module failures and OOM (HTTP/module fixtures)");
}
'''
with tempfile.TemporaryDirectory(prefix='ops-api-') as directory:
    path=Path(directory);c=path/'test.c';binary=path/('test.exe' if os.name=='nt' else 'test')
    c.write_text(fixture+woltype+types+adapters+function(wolsource,'bool wol_parse_mac(')+''.join(function(source,s) for s in (
        'static bool integer(', 'static bool boolean(', 'static bool unique(', 'static esp_err_t send_json(', 'static esp_err_t post_ops('))+tests,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-g','-I',str(ROOT/'main')];libs=['-lm'];dep=os.environ.get('CJSON_SOURCE')
    if dep:flags+=['-I',str(Path(dep).parent),dep]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split();libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('OPS_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(['gcc',*flags,str(c),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)

# Second program: actual Service Gateway export helper. Synthetic identifiers
# must never appear in the sanitized output; every allocation failure is clean.
EXPORT=r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "service_check.h"
#include "service_evidence.h"
#include "service_diagnostics.h"
static int rows=2;static bool replied=true;
static tailnet_forward_rule_t rules[2]={
 {.valid=1,.enabled=1,.proto=6,.source_prefix=32,.source_network=0xc0a8012a,.listen_port=18830,.destination_port=1883,.name="SecretBrokerName",.destination="broker.private-tailnet.ts.net"},
 {.valid=1,.enabled=0,.proto=17,.source_prefix=24,.source_network=0xc0a80100,.listen_port=15514,.destination_port=514,.name="HiddenSyslog",.destination="100.64.77.88"}};
static tailnet_forward_runtime_t runtime[2]={{.installed=true,.resolved_ip=0x64400a0b,.accepted_packets=9,.blocked_packets=1,.last_accepted_s=95,.last_blocked_s=90},
 {.installed=false,.resolved_ip=0,.error="private.example detail"}};
static int64_t esp_timer_get_time(void){return 100000000;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){if(i>=rows)return false;*r=rules[i];*rt=runtime[i];return true;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){return r->listen_port;}
bool service_check_get(int i,uint32_t t,service_check_result_t *out){(void)t;if(i)return false;*out=(service_check_result_t){.state=SC_REACHABLE,.token=t};return true;}
const char *service_check_state_name(unsigned s){return s==SC_REACHABLE?"reachable":"not_tested";}
bool ml_policy_reply_age(uint8_t p,const uint8_t ip[4],uint16_t port,uint32_t *age){(void)p;(void)ip;(void)port;if(replied)*age=3000;return replied;}
''' + function(source,'static bool export_service_rules(') + r'''
static unsigned allocations,fail_at;
static void *allocate(size_t n){return ++allocations==fail_at?NULL:malloc(n);}
int main(void){
 cJSON *root=cJSON_CreateObject();assert(export_service_rules(root));
 char *text=cJSON_PrintUnformatted(root);assert(text);
 const char *forbidden[]={"SecretBrokerName","HiddenSyslog","broker.private","100.64.77.88","100.64.10.11","192.168","18830","1883","514","private.example"};
 for(unsigned i=0;i<sizeof forbidden/sizeof *forbidden;i++)assert(!strstr(text,forbidden[i]));
 cJSON *a=cJSON_GetObjectItem(root,"service_gateway_rules");assert(cJSON_GetArraySize(a)==2);
 cJSON *x=cJSON_GetArrayItem(a,0),*y=cJSON_GetArrayItem(a,1);
 assert(!strcmp(cJSON_GetObjectItem(x,"diagnostic")->valuestring,"service_replied")&&cJSON_IsTrue(cJSON_GetObjectItem(x,"single_source")));
 assert(cJSON_GetObjectItem(x,"service_reply_age_s")->valuedouble==3&&cJSON_GetObjectItem(x,"last_accepted_age_s")->valuedouble==6);
 assert(!strcmp(cJSON_GetObjectItem(x,"destination_check")->valuestring,"reachable"));
 assert(!strcmp(cJSON_GetObjectItem(y,"diagnostic")->valuestring,"disabled")&&!strcmp(cJSON_GetObjectItem(y,"protocol")->valuestring,"udp"));
 assert(cJSON_IsNull(cJSON_GetObjectItem(y,"service_reply_age_s"))&&cJSON_IsNull(cJSON_GetObjectItem(y,"last_accepted_age_s"))&&cJSON_IsTrue(cJSON_GetObjectItem(y,"runtime_error")));
 free(text);cJSON_Delete(root);
 rows=0;root=cJSON_CreateObject();assert(export_service_rules(root)&&cJSON_GetArraySize(cJSON_GetObjectItem(root,"service_gateway_rules"))==0);cJSON_Delete(root);rows=2;
 cJSON_Hooks hooks={allocate,free};cJSON_InitHooks(&hooks);
 allocations=0;fail_at=0;root=cJSON_CreateObject();assert(export_service_rules(root));cJSON_Delete(root);unsigned total=allocations;
 for(unsigned f=2;f<=total;f++){allocations=0;fail_at=f;root=cJSON_CreateObject();assert(root);assert(!export_service_rules(root));cJSON_Delete(root);}
 cJSON_InitHooks(NULL);
 puts("PASS: actual Service Gateway export excludes names/destinations/IPs/ports/CIDRs/errors, evidence fields, every allocation failure (fixtures)");
}
'''
STUBS={'esp_err.h':'#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n','lwip/pbuf.h':'#pragma once\nstruct pbuf;\n','lwip/netif.h':'#pragma once\nstruct netif;\n'}
with tempfile.TemporaryDirectory(prefix='ops-export-') as directory:
    path=Path(directory);(path/'lwip').mkdir()
    for name,text in STUBS.items():(path/name).write_text(text)
    c=path/'export.c';c.write_text(EXPORT,encoding='utf-8');binary=path/('export.exe' if os.name=='nt' else 'export')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-g','-I',str(path),'-I',str(ROOT/'main'),'-I',str(ROOT/'external/microlink/components/microlink/include')];libs=['-lm'];dep=os.environ.get('CJSON_SOURCE')
    if dep:flags+=['-I',str(Path(dep).parent),dep]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split();libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('OPS_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(['gcc',*flags,str(c),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
