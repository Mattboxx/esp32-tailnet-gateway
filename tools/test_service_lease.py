"""Actual lease C with synthetic clocks/NVS/locks/rules. Not physical expiry."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/service_lease.c').read_text(encoding='utf-8')
source=re.sub(r'^#include[^\n]*\n','',source,flags=re.M)
header=(ROOT/'main/tailnet_forward.h').read_text(encoding='utf-8')
model=header[header.index('typedef struct'):header.index('} tailnet_forward_rule_t;')+len('} tailnet_forward_rule_t;')]
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include "cJSON.h"
#define TAILNET_FORWARD_MAX 8
#define TAILNET_FORWARD_NAME_LEN 32
#define TAILNET_FORWARD_DEST_LEN 96
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_INVALID_STATE 3
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define NVS_NAMESPACE "fixture"
#define portMAX_DELAY 0
#define portMUX_INITIALIZER_UNLOCKED 0
typedef int esp_err_t,nvs_handle_t,SemaphoreHandle_t,StaticSemaphore_t,portMUX_TYPE;
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
static int xSemaphoreCreateMutexStatic(void *p){(void)p;return 1;}
static void xSemaphoreTake(int h,int wait){assert(h);(void)wait;}
static void xSemaphoreGive(int h){assert(h);}
static void forwarding_config_lock(void){}
static void forwarding_config_unlock(void){}
static time_t wall=1800000000;
static uint64_t milliseconds=1000;
static unsigned closure_events;
static void homelab_ops_service_closed(unsigned count){assert(count&&count<=8);closure_events+=count;}
static time_t fake_time(time_t *out){if(out)*out=wall;return wall;}
#define time fake_time
static int64_t esp_timer_get_time(void){return (int64_t)milliseconds*1000;}
static unsigned char image[2048],pending[2048];static size_t image_size,pending_size;
static unsigned fail;
static int nvs_open(const char *s,int mode,nvs_handle_t *h){(void)s;(void)mode;*h=1;return fail==1?-1:0;}
static int nvs_get_blob(int h,const char *key,void *out,size_t *n){(void)h;(void)key;if(!image_size)return ESP_ERR_NVS_NOT_FOUND;if(*n<image_size)return -1;*n=image_size;memcpy(out,image,image_size);return 0;}
static int nvs_set_blob(int h,const char *key,const void *data,size_t n){(void)h;(void)key;assert(n<sizeof pending);if(fail==2)return -1;memcpy(pending,data,n);pending_size=n;return 0;}
static int nvs_commit(int h){(void)h;if(fail==3)return -1;memcpy(image,pending,pending_size);image_size=pending_size;return 0;}
static void nvs_close(int h){(void)h;}
bool service_lease_tick(void);
esp_err_t service_lease_set_mode(int,uint32_t,uint32_t,bool,bool);
'''
stub=r'''
static tailnet_forward_rule_t rule={.valid=1,.enabled=1,.proto=6,.source_prefix=24,.listen_port=2222,.destination_port=22,.name="synthetic",.destination="100.64.0.1"};
static int position;
static tailnet_forward_rule_t other={.valid=1,.enabled=1,.proto=6,.source_prefix=24,.listen_port=3333,.destination_port=443,.name="other",.destination="100.64.0.2"};
static int tailnet_forward_count(void){return 2;}
static bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,void *runtime){(void)runtime;if(i<0||i>1)return false;*r=i==position?rule:other;return true;}
'''
tests=r'''
static void reboot(void){loaded=ready=false;writer=0;last_wall=0;next_persist_retry=0;memset(deadlines,0,sizeof deadlines);memset(expired,0,sizeof expired);service_lease_init();}
int main(void){
    service_lease_init();assert(service_lease_allowed(0,&rule));uint32_t token=service_lease_token(&rule);
    assert(service_lease_set(0,token,120,false)==ESP_OK);assert(service_lease_allowed(0,&rule));
    assert(service_lease_allowed(1,&rule)); /* Active binding survives reindex. */
    assert(service_lease_allowed(1,&other)); /* Existing permanent binding retained. */
    tailnet_forward_rule_t changed=rule;changed.destination_port=23;assert(!service_lease_allowed(0,&changed));
    changed=rule;changed.enabled=0;assert(service_lease_allowed(0,&changed));
    for(fail=1;fail<=3;fail++)assert(service_lease_set(0,token,0,true)!=ESP_OK);
    fail=0;assert(saved.entries[0].token==token);milliseconds+=121000;
    assert(!service_lease_allowed(0,&rule));wall+=121;assert(service_lease_tick());
    assert(closure_events==1);assert(!service_lease_tick());assert(closure_events==1);
    assert(!service_lease_allowed(0,&rule));assert(saved.entries[0].expires==0);
    assert(!service_lease_allowed(1,&rule)); /* Moving an expired rule must NOT make it permanent. */
    reboot();assert(!service_lease_allowed(0,&rule));assert(closure_events==1);
    assert(service_lease_set(0,token,120,false)==ESP_OK);wall=0;reboot();assert(!service_lease_allowed(0,&rule));
    wall=1800000122;assert(service_lease_tick());assert(service_lease_allowed(0,&rule));
    wall--;assert(service_lease_tick());assert(!service_lease_allowed(0,&rule));reboot();assert(!service_lease_allowed(0,&rule));
    assert(service_lease_set(0,token+1,120,false)==ESP_ERR_INVALID_STATE);
    assert(service_lease_set(0,token,59,false)==ESP_ERR_INVALID_ARG);
    assert(service_lease_set(0,token,604801,false)==ESP_ERR_INVALID_ARG);
    assert(service_lease_set(0,token,0,true)==ESP_OK);assert(service_lease_allowed(0,&rule));
    position=1;assert(service_lease_set(1,token,120,false)==ESP_OK);assert(service_lease_allowed(1,&rule));
    assert(service_lease_allowed(0,&other));milliseconds+=121000;wall+=121;(void)service_lease_tick();
    assert(!service_lease_allowed(1,&rule));changed=rule;changed.destination_port=25;
    assert(!service_lease_allowed(0,&changed)&&!service_lease_allowed(1,&changed)); /* Edit + move cannot escape timer. */
    rule=changed;token=service_lease_token(&rule);assert(service_lease_set(1,token,0,true)==ESP_OK);
    assert(service_lease_allowed(1,&rule)&&service_lease_allowed(0,&other));
    assert(service_lease_set_mode(1,token,60,false,true)==ESP_OK);assert(!service_lease_delete_requested(&rule));
    milliseconds+=61000;wall+=61;assert(service_lease_delete_requested(&rule));assert(!service_lease_allowed(0,&rule));
    (void)service_lease_tick();reboot();assert(service_lease_delete_requested(&rule));
    assert(service_lease_set_mode(1,token,0,true,true)==ESP_ERR_INVALID_ARG);
    assert(service_lease_set_mode(1,token,0,true,false)==ESP_OK);assert(!service_lease_delete_requested(&rule));
    cJSON *j=service_lease_snapshot();assert(j&&cJSON_GetArraySize(j)==2);cJSON_Delete(j);
    /* Exact old record length: v1 has no delete mask or permanent identities. */
    lease_store_t legacy={.magic=saved.magic,.version=1};
    legacy.entries[0]=(lease_t){.token=token,.created=(uint32_t)wall,.expires=(uint32_t)wall+120};
    image_size=offsetof(lease_store_t,delete_mask);memcpy(image,&legacy,image_size);reboot();
    assert(ready&&saved.version==3&&service_lease_allowed(1,&rule));
    assert(!service_lease_allowed(0,&other)); /* Unknown old permanent identity is NOT invented. */
    legacy.version=2;legacy.entries[0]=(lease_t){.token=token};
    memcpy(image,&legacy,image_size);reboot();assert(ready&&service_lease_allowed(1,&rule));
    legacy.entries[1]=legacy.entries[0];memcpy(image,&legacy,image_size);reboot();assert(!ready); /* Ambiguous identities. */
    legacy.entries[1]=(lease_t){0};memcpy(image,&legacy,image_size);reboot();assert(ready);
    image[0]^=1;reboot();assert(!service_lease_allowed(0,&rule)); /* Corrupt store never defaults open. */
    puts("PASS: actual leases: persistence faults, expiry before tick, reboot, clock missing/rollback, changed rule and explicit permanent action (host fixtures)");
}
'''
with tempfile.TemporaryDirectory(prefix='service-lease-') as directory:
    path=Path(directory);c=path/'test.c';binary=path/('test.exe' if os.name=='nt' else 'test');c.write_text(fixture+model+stub+source+tests,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-g'];libs=[];dep=os.environ.get('CJSON_SOURCE')
    if dep:flags+=['-I',str(Path(dep).parent),dep]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split();libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('LEASE_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(['gcc',*flags,str(c),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
