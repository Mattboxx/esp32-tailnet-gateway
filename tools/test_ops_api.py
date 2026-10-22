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
