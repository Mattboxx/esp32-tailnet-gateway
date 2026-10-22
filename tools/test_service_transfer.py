"""Actual import/export HTTP/parser with synthetic auth/NVS/config-owner sinks.
Not a real browser/session/device/power-loss test. Uses actual JSON guard.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=re.sub(r'^#include[^\n]*\n','',(ROOT/'main/service_transfer.c').read_text(encoding='utf-8'),flags=re.M)
FIXTURE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#define HTTPD_400_BAD_REQUEST 400
#define HTTP_GET 0
#define HTTP_POST 1
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
typedef int esp_err_t,httpd_handle_t;
typedef struct {const char *body;int content_len,offset,status;char response[8192];} httpd_req_t;
typedef struct {const char *uri;int method;int (*handler)(httpd_req_t*);} httpd_uri_t;
#include "tailnet_forward.h"
#include "json_guard.h"
static bool authenticated=true,read_fail;
static unsigned alloc_calls,alloc_fail,apply_calls,preview_calls,mqtt_changes;
static int owner_error,owner_depth;
static char owner_guard[TAILNET_TABLE_GUARD_LEN]="0000000000000001-1111111111111111";
static int web_ui_require_auth(httpd_req_t *r){if(authenticated)return 0;r->status=401;return -1;}
static void *heap_caps_calloc(size_t n,size_t size,int caps){(void)caps;return ++alloc_calls==alloc_fail?NULL:calloc(n,size);}
static int httpd_resp_send_500(httpd_req_t *r){r->status=500;return 0;}
static int httpd_resp_send_408(httpd_req_t *r){r->status=408;return 0;}
static int httpd_resp_send_err(httpd_req_t *r,int status,const char *why){(void)why;r->status=status;return 0;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;assert(!strcmp(s,"application/json"));return 0;}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){(void)r;assert(k&&v);return 0;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){assert(strlen(s)<sizeof r->response);strcpy(r->response,s);return 0;}
static int httpd_req_recv(httpd_req_t *r,char *to,int n){if(read_fail)return -1;assert(r->offset+n<=r->content_len);memcpy(to,r->body+r->offset,n);r->offset+=n;return n;}
static int httpd_register_uri_handler(int server,const httpd_uri_t *route){(void)server;assert(route&&route->handler);return 0;}
static void mqtt_integration_tailnet_forward_changed(void){mqtt_changes++;}
static void forwarding_config_lock(void){assert(!owner_depth);owner_depth++;}
static void forwarding_config_unlock(void){assert(owner_depth==1);owner_depth--;}
int tailnet_forward_count(void){return 1;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){
    (void)rt;if(i)return false;*r=(tailnet_forward_rule_t){.valid=1,.enabled=1,.proto=6,.listen_port=2222,.destination_port=22,.name="fixture",.destination="100.64.0.1",.source_prefix=24};return true;
}
int tailnet_forward_parse_cidr(const char *s,uint32_t *network,uint8_t *prefix){if(strcmp(s,"192.0.2.0/24"))return ESP_ERR_INVALID_ARG;*network=0xc0000200;*prefix=24;return 0;}
void tailnet_forward_format_cidr(uint32_t n,uint8_t p,char *out,size_t cap){(void)n;(void)p;snprintf(out,cap,"192.0.2.0/24");}
int tailnet_forward_replace_guarded(const tailnet_forward_rule_t *r,int count,const char *expected,bool apply,tailnet_forward_preview_t *preview,char *error,size_t cap){
    preview_calls++;for(int i=0;i<count;i++)assert(!r[i].enabled);strcpy(preview->guard,owner_guard);preview->previous_count=1;preview->previous_enabled=1;
    if(owner_error)return owner_error;
    if(apply&&strcmp(expected,owner_guard)){snprintf(error,cap,"Configuration changed");return ESP_ERR_INVALID_STATE;}
    if(apply){apply_calls++;strcpy(owner_guard,"0000000000000002-2222222222222222");strcpy(preview->guard,owner_guard);}return 0;
}
'''
TESTS=r'''
static cJSON *request(const char *action){
    cJSON *j=json_guard_parse("{\"format\":\"homelab-service-rules/v1\",\"rules\":[{\"name\":\"fixture\",\"enabled\":true,\"protocol\":\"tcp\",\"listen_port\":2222,\"tailnet_destination\":\"100.64.0.1\",\"destination_port\":22,\"allowed_source_subnet\":\"192.0.2.0/24\"}]}");assert(j);cJSON_AddStringToObject(j,"action",action);return j;
}
static httpd_req_t submit(cJSON *j){char *text=cJSON_PrintUnformatted(j);assert(text);httpd_req_t r={.body=text,.content_len=(int)strlen(text),.status=200};alloc_calls=0;transfer_import(&r);cJSON_Delete(j);free(text);r.body=NULL;return r;}
int main(void){
    httpd_req_t r=submit(request("preview"));assert(r.status==200&&!apply_calls);
    cJSON *reply=json_guard_parse(r.response);assert(reply&&cJSON_IsFalse(cJSON_GetObjectItem(reply,"applied")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(reply,"rules"),0),"enabled")));cJSON_Delete(reply);
    r=submit(request("apply"));assert(r.status==400&&!apply_calls);
    cJSON *j=request("apply");cJSON_AddStringToObject(j,"expected_guard",owner_guard);cJSON_AddBoolToObject(j,"confirm_replace",true);
    r=submit(j);assert(r.status==200&&apply_calls==1&&mqtt_changes==1);
    j=request("apply");cJSON_AddStringToObject(j,"expected_guard","0000000000000001-1111111111111111");cJSON_AddBoolToObject(j,"confirm_replace",true);
    r=submit(j);assert(r.status==409&&apply_calls==1);
    j=request("preview");cJSON_AddStringToObject(cJSON_GetArrayItem(cJSON_GetObjectItem(j,"rules"),0),"source_identity","unsupported");
    assert(submit(j).status==400&&apply_calls==1);
    j=request("preview");cJSON_ReplaceItemInObject(j,"format",cJSON_CreateString("future/v99"));assert(submit(j).status==400);
    for(alloc_fail=1;alloc_fail<=2;alloc_fail++)assert(submit(request("preview")).status==500);
    alloc_fail=0;
    authenticated=false;assert(submit(request("preview")).status==401);authenticated=true;
    read_fail=true;assert(submit(request("preview")).status==408);read_fail=false;
    owner_error=ESP_FAIL;assert(submit(request("preview")).status==500&&apply_calls==1);owner_error=0;
    r=(httpd_req_t){.status=200};transfer_export(&r);assert(r.status==200);reply=json_guard_parse(r.response);assert(reply&&cJSON_GetArraySize(cJSON_GetObjectItem(reply,"rules"))==1);
    assert(!cJSON_GetObjectItem(reply,"password")&&!cJSON_GetObjectItem(reply,"expected_guard"));cJSON_Delete(reply);
    assert(service_transfer_register_http(1)==0&&!owner_depth);
    puts("PASS: actual service transfer parser/HTTP preview, explicit disabled import, stale-selector refusal, auth/type/OOM/read/module failures and config-only export (mock owner/session)");
}
'''
with tempfile.TemporaryDirectory(prefix='service-transfer-') as folder:
    p=Path(folder);(p/'lwip').mkdir();(p/'esp_err.h').write_text('/* supplied */\n')
    for name in ('netif','pbuf'):(p/'lwip'/f'{name}.h').write_text('#pragma once\nstruct '+name+';\n')
    (p/'test.c').write_text(FIXTURE+source+TESTS);binary=p/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'main')];libs=[]
    cjson=os.environ.get('CJSON_SOURCE')
    if cjson:flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('TRANSFER_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
