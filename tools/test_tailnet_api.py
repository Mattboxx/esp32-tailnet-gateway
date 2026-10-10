"""Exercise the actual Tailnet HTTP save handler with real cJSON requests.

No device/network access. TAILNET_SANITIZE=1 enables ASan/UBSan in CI.
Persistence is injected; actual rule/NVS behavior is covered by test_tailnet_state.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/web_ui.c').read_text(encoding='utf-8')
functions='static bool json_port_value'+source.split('static bool json_port_value',1)[1].split('static const httpd_uri_t uri_tailnet_forward=',1)[0]
fixture=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "cJSON.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#define HTTPD_400_BAD_REQUEST 400
#include "tailnet_forward.h"
typedef struct { const char *body; int status; char response[256]; } httpd_req_t;
static bool authenticated=true, allocation_fails;
static unsigned save_calls, mqtt_changes;
static int save_result;
static tailnet_forward_rule_t last_rules[TAILNET_FORWARD_MAX];
static int last_count;
static size_t strlcpy(char *d,const char *s,size_t z) {
    size_t n=strlen(s); if(z) { size_t k=n<z-1?n:z-1; memcpy(d,s,k); d[k]=0; } return n;
}
static esp_err_t require_auth(httpd_req_t *r) { if(authenticated)return ESP_OK; r->status=401; return ESP_FAIL; }
static char *malloc_body_buf(size_t n) { return allocation_fails?NULL:malloc(n); }
static esp_err_t recv_body(httpd_req_t *r,char *to,size_t capacity,void *unused) {
    (void)unused; size_t n=strlen(r->body); assert(n<capacity); memcpy(to,r->body,n+1); return ESP_OK;
}
static esp_err_t httpd_resp_send_500(httpd_req_t *r) { r->status=500; return ESP_OK; }
static esp_err_t httpd_resp_send_err(httpd_req_t *r,int code,const char *why) { r->status=code; strlcpy(r->response,why,sizeof r->response); return ESP_OK; }
static esp_err_t httpd_resp_set_status(httpd_req_t *r,const char *status) { r->status=atoi(status); return ESP_OK; }
static esp_err_t httpd_resp_sendstr(httpd_req_t *r,const char *s) { strlcpy(r->response,s,sizeof r->response); return ESP_OK; }
static esp_err_t httpd_resp_set_type(httpd_req_t *r,const char *type) { (void)r; assert(!strcmp(type,"application/json")); return ESP_OK; }
static void mqtt_integration_tailnet_forward_changed(void) { ++mqtt_changes; }
esp_err_t tailnet_forward_parse_cidr(const char *s,uint32_t *net,uint8_t *prefix) {
    if(strcmp(s,"192.0.2.0/24"))return ESP_ERR_INVALID_ARG;
    *net=0xc0000200; *prefix=24; return ESP_OK;
}
esp_err_t tailnet_forward_set_all(const tailnet_forward_rule_t *r,int n,char *why,size_t capacity) {
    ++save_calls; last_count=n; memcpy(last_rules,r,n*sizeof *r);
    if(save_result==ESP_ERR_INVALID_STATE)strlcpy(why,"port conflict",capacity);
    return save_result;
}
'''
tests=r'''
static cJSON *request(void) {
    cJSON *root=cJSON_CreateObject(), *arr=cJSON_AddArrayToObject(root,"rules"), *rule=cJSON_CreateObject();
    cJSON_AddStringToObject(rule,"name","Synthetic SSH"); cJSON_AddBoolToObject(rule,"enabled",true);
    cJSON_AddStringToObject(rule,"protocol","tcp"); cJSON_AddNumberToObject(rule,"listen_port",2222);
    cJSON_AddStringToObject(rule,"tailnet_destination","100.64.0.2"); cJSON_AddNumberToObject(rule,"destination_port",22);
    cJSON_AddStringToObject(rule,"allowed_source_subnet","192.0.2.0/24"); cJSON_AddItemToArray(arr,rule); return root;
}
static cJSON *row(cJSON *root) { return cJSON_GetArrayItem(cJSON_GetObjectItem(root,"rules"),0); }
static httpd_req_t send(cJSON *root) {
    char *body=cJSON_PrintUnformatted(root); assert(body); httpd_req_t r={.body=body,.status=200};
    save_calls=mqtt_changes=0; (void)tailnet_forward_save_handler(&r); free(body); cJSON_Delete(root); r.body=NULL; return r;
}
int main(void) {
    for(unsigned kind=0;kind<7;kind++) {
        cJSON *root=request(), *value;
        switch(kind) {
        case 0: value=cJSON_CreateString("false"); break;
        case 1: value=cJSON_CreateString("true"); break;
        case 2: value=cJSON_CreateNumber(0); break;
        case 3: value=cJSON_CreateNumber(1); break;
        case 4: value=cJSON_CreateNull(); break;
        case 5: value=cJSON_CreateArray(); break;
        default: value=cJSON_CreateObject(); break;
        }
        cJSON_ReplaceItemInObjectCaseSensitive(row(root),"enabled",value);
        httpd_req_t r=send(root); assert(r.status==400 && !save_calls && !mqtt_changes);
    }
    cJSON *root=request(); cJSON_DeleteItemFromObjectCaseSensitive(row(root),"enabled");
    assert(send(root).status==400 && !save_calls);
    char long_value[121]; memset(long_value,'a',120); long_value[120]=0;
    for(unsigned field=0;field<2;field++) {
        root=request(); cJSON_ReplaceItemInObjectCaseSensitive(row(root),field?"name":"tailnet_destination",cJSON_CreateString(long_value));
        assert(send(root).status==400 && !save_calls);
    }
    root=request(); cJSON_ReplaceItemInObjectCaseSensitive(row(root),"name",cJSON_CreateNumber(5));
    assert(send(root).status==400 && !save_calls);
    for(unsigned enabled=0;enabled<2;enabled++) {
        root=request(); cJSON_ReplaceItemInObjectCaseSensitive(row(root),"enabled",cJSON_CreateBool(enabled));
        assert(send(root).status==200 && save_calls==1 && mqtt_changes==1 && last_count==1 && last_rules[0].enabled==enabled);
    }
    root=request(); cJSON_ReplaceItemInObjectCaseSensitive(row(root),"listen_port",cJSON_CreateNumber(22.5));
    assert(send(root).status==400 && !save_calls);
    root=request(); cJSON_ReplaceItemInObjectCaseSensitive(row(root),"destination_port",cJSON_CreateString("65536"));
    assert(send(root).status==400 && !save_calls);
    for(int error=-1;error>=-3;error--) {
        save_result=error; httpd_req_t r=send(request());
        assert(r.status==(error==ESP_ERR_INVALID_STATE?409:error==ESP_ERR_INVALID_ARG?400:500));
        assert(save_calls==1 && !mqtt_changes);
    }
    save_result=ESP_OK; authenticated=false; assert(send(request()).status==401 && !save_calls);
    authenticated=true; allocation_fails=true; assert(send(request()).status==500 && !save_calls); allocation_fails=false;
    root=request(); cJSON *arr=cJSON_GetObjectItem(root,"rules");
    for(unsigned i=0;i<TAILNET_FORWARD_MAX;i++)cJSON_AddItemToArray(arr,cJSON_Duplicate(row(root),true));
    assert(send(root).status==400 && !save_calls);
    root=cJSON_CreateObject(); cJSON_AddArrayToObject(root,"rules");
    assert(send(root).status==200 && save_calls==1 && mqtt_changes==1 && last_count==0);
    puts("PASS: actual Tailnet HTTP handler rejects nonboolean/missing enable and oversized/wrong-type labels/destinations, preserves explicit ON/OFF, auth and ports; maps persistence failure to 500 and conflict to 409");
}
'''
with tempfile.TemporaryDirectory(prefix='tailnet-api-') as directory:
    path=Path(directory); (path/'lwip').mkdir()
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n',encoding='utf-8')
    (path/'lwip/pbuf.h').write_text('#pragma once\nstruct pbuf;\n',encoding='utf-8')
    (path/'lwip/netif.h').write_text('#pragma once\nstruct netif;\n',encoding='utf-8')
    (path/'test.c').write_text(fixture+functions+tests,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(path),'-I',str(ROOT/'main')]
    libs=[]; cjson=os.environ.get('CJSON_SOURCE')
    if cjson: flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('TAILNET_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True)
