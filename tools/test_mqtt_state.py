"""Actual MQTT state rule array and budget fitting, synthetic worst case.

Compiles add_tailnet_rules()/state_print_fitted() from main/mqtt_integration.c
with fixture rules/evidence and a synthetic operations object (12 maximum
devices). Prints measured sizes. Not a measurement of the whole on-device
state, broker behavior or Home Assistant. MQTTSTATE_SANITIZE=1 adds ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
start = '#define MQTT_STATE_BUDGET'
helpers = start + source.split(start, 1)[1].split('static void publish_state(void)', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "service_evidence.h"
static int rows=8;static tailnet_forward_rule_t rules[TAILNET_FORWARD_MAX];static tailnet_forward_runtime_t rts[TAILNET_FORWARD_MAX];
int tailnet_forward_count(void){return rows;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){if(i<0||i>=rows)return false;*r=rules[i];*rt=rts[i];return true;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){return r->listen_port+1u;}
bool service_check_get(int i,uint32_t t,service_check_result_t *out){(void)t;*out=(service_check_result_t){.state=(uint8_t)(i%2?SC_NO_ANSWER:SC_UDP_UNVERIFIABLE),.token=t};return true;}
const char *service_check_state_name(unsigned s){return s==SC_NO_ANSWER?"no_tcp_answer":s==SC_UDP_UNVERIFIABLE?"udp_unverifiable":"not_tested";}
bool ml_policy_reply_age(uint8_t p,const uint8_t ip[4],uint16_t port,uint32_t *age){(void)p;(void)ip;(void)port;*age=4294967295u;return true;}
''' + helpers + r'''
static unsigned allocations,fail_at;
static void *allocate(size_t n){return ++allocations==fail_at?NULL:malloc(n);}
static cJSON *state(size_t filler){
    cJSON *root=cJSON_CreateObject();assert(root);
    char *pad=malloc(filler+1);memset(pad,'x',filler);pad[filler]=0;cJSON_AddStringToObject(root,"filler",pad);free(pad);
    cJSON *ops=cJSON_AddObjectToObject(root,"operations"),*dev=cJSON_AddArrayToObject(ops,"devices");
    cJSON_AddStringToObject(ops,"recovery_state","waiting-for-host");cJSON_AddNumberToObject(ops,"internal_largest",123456);
    cJSON_AddNumberToObject(ops,"sockets_used",9);cJSON_AddNumberToObject(ops,"service_closures",3);cJSON_AddObjectToObject(ops,"health");
    for(int d=0;d<12;d++){cJSON *x=cJSON_CreateObject();char t[96];memset(t,'n',95);t[95]=0;cJSON_AddStringToObject(x,"name",t);cJSON_AddStringToObject(x,"target",t);cJSON_AddItemToArray(dev,x);}
    cJSON_AddArrayToObject(ops,"events");cJSON_AddArrayToObject(root,"forwarding_leases");
    assert(add_tailnet_rules(root,false));return root;
}
static size_t rules_size(bool compact){
    cJSON *r=cJSON_CreateObject();assert(add_tailnet_rules(r,compact));char *j=cJSON_PrintUnformatted(r);size_t n=strlen(j);free(j);cJSON_Delete(r);return n;
}
int main(void){
    for(int i=0;i<TAILNET_FORWARD_MAX;i++){
        rules[i]=(tailnet_forward_rule_t){.valid=1,.enabled=1,.proto=(uint8_t)(i%2?6:17),.listen_port=(uint16_t)(65535-i),.destination_port=65535};
        memset(rules[i].name,'"',sizeof rules[i].name-1); /* worst-case JSON escaping */
        memset(rules[i].destination,'\\',sizeof rules[i].destination-1);
        rts[i]=(tailnet_forward_runtime_t){.installed=true,.resolved_ip=0x64400001u+i,.last_accepted_s=1,.last_blocked_s=1};
    }
    size_t full=rules_size(false),compact=rules_size(true);
    printf("MEASURED: 8 worst-case rules %zu bytes full, %zu bytes compact\n",full,compact);
    assert(compact<full/2&&compact<1400);
    /* Compact output never contains names/destinations/ports. */
    cJSON *r=cJSON_CreateObject();assert(add_tailnet_rules(r,true));char *j=cJSON_PrintUnformatted(r);
    assert(!strstr(j,"\\\\")&&!strstr(j,"65535")&&!strstr(j,"\"name\"")&&strstr(j,"\"status\"")&&strstr(j,"\"enabled\""));free(j);cJSON_Delete(r);
    unsigned level;
    /* Small state: untouched, level 0. */
    cJSON *root=state(10);
    cJSON_DeleteItemFromObject(cJSON_GetObjectItem(root,"operations"),"devices");
    char *out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);assert(out&&level==0&&strlen(out)<=MQTT_STATE_BUDGET&&strstr(out,"\"destination\""));free(out);cJSON_Delete(root);
    /* Device list pushes it over: level 1 drops detail, keeps HA fields. */
    root=state(1500);out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);
    printf("MEASURED: level %u, %zu bytes (budget %u)\n",level,strlen(out),MQTT_STATE_BUDGET);
    assert(level==1&&strlen(out)<=MQTT_STATE_BUDGET&&!strstr(out,"\"devices\"")&&strstr(out,"\"recovery_state\"")&&strstr(out,"\"service_closures\"")
           &&strstr(out,"\"forwarding_leases\"")&&strstr(out,"\"state_compact_level\":1"));free(out);cJSON_Delete(root);
    /* Still over: level 2 compacts rule labels, keeps enabled/status per rule. */
    root=state(3500);out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);
    printf("MEASURED: level %u, %zu bytes\n",level,strlen(out));
    assert(level==2&&strlen(out)<=MQTT_STATE_BUDGET&&!strstr(out,"\"destination\"")&&strstr(out,"\"state_compact_level\":2"));
    cJSON *parsed=cJSON_Parse(out);assert(cJSON_GetArraySize(cJSON_GetObjectItem(parsed,"tailnet_forward_rules"))==8);
    assert(!strcmp(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(parsed,"tailnet_forward_rules"),7),"status")->valuestring,"service_replied"));
    cJSON_Delete(parsed);free(out);cJSON_Delete(root);
    /* Hopeless: returns the oversize payload (caller logs), never NULL or loops. */
    root=state(9000);out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);assert(out&&level==2&&strlen(out)>MQTT_STATE_BUDGET);free(out);cJSON_Delete(root);
    /* Every allocation failure: false/NULL, no crash (leaks caught by sanitizers). */
    cJSON_Hooks hooks={allocate,free};cJSON_InitHooks(&hooks);
    allocations=0;fail_at=0;r=cJSON_CreateObject();assert(add_tailnet_rules(r,false));cJSON_Delete(r);unsigned total=allocations;
    for(unsigned f=2;f<=total;f++){allocations=0;fail_at=f;r=cJSON_CreateObject();assert(!add_tailnet_rules(r,false));cJSON_Delete(r);}
    cJSON_InitHooks(NULL);
    root=state(3500);cJSON_InitHooks(&hooks);allocations=0;fail_at=0;out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);free(out);total=allocations;cJSON_InitHooks(NULL);cJSON_Delete(root);
    for(unsigned f=1;f<=total;f++){root=state(3500);cJSON_InitHooks(&hooks);allocations=0;fail_at=f;out=state_print_fitted(root,MQTT_STATE_BUDGET,&level);cJSON_InitHooks(NULL);free(out);cJSON_Delete(root);}
    puts("PASS: actual MQTT rule array (full/compact, escaping, no identifiers when compact), budget levels 0/1/2/oversize, every allocation failure (fixtures)");
}
'''

STUBS = {'esp_err.h': '#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n', 'lwip/pbuf.h': '#pragma once\nstruct pbuf;\n', 'lwip/netif.h': '#pragma once\nstruct netif;\n'}
with tempfile.TemporaryDirectory(prefix='mqtt-state-') as folder:
    path = Path(folder); (path / 'lwip').mkdir()
    for name, text in STUBS.items(): (path / name).write_text(text)
    c = path / 'test.c'; c.write_text(PROGRAM, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main'),
             '-I', str(ROOT / 'external/microlink/components/microlink/include')]
    libs = []
    dep = os.environ.get('CJSON_SOURCE')
    if dep: flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('MQTTSTATE_SANITIZE') == '1': flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
