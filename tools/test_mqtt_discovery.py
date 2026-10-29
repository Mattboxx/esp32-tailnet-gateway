"""Actual entity serializer and batch cursor. MQTT acceptance is mocked, not HA."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'main/mqtt_integration.c').read_text();src='static bool add_device'+src.split('static bool add_device',1)[1].split('static void normalized_mac',1)[0]
PROGRAM=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "discovery_budget.h"
typedef struct {char discovery_prefix[48];} mqtt_integration_config_t;
static void mqtt_integration_get_config(mqtt_integration_config_t *c){strcpy(c->discovery_prefix,"homeassistant");}
static discovery_budget_t s_discovery;
static char s_device_id[24]="fixture",s_availability_topic[128]="fixture/availability";
static unsigned accepted,allocations,fail_at,live;
static int publish_result=1;
static int publish(const char *t,const char *j,int retain){assert(t&&j&&retain);if(strstr(t,"/event/")){assert(strstr(j,"\"event_types\":[\"possible_blackout\"]"));assert(strstr(j,"\"qos\":1"));}if(publish_result>=0)accepted++;return publish_result;}
static void *allocate(size_t n){if(++allocations==fail_at)return NULL;void *p=malloc(n);if(p)live++;return p;}
static void release(void *p){if(p)live--;free(p);}
'''
TAIL=r'''
static void one(void){discovery_publish_entity("sensor","one","Fixture","fixture/state","{{ value_json.one }}",NULL,NULL,"B");}
int main(void){
    cJSON_Hooks hooks={allocate,release};cJSON_InitHooks(&hooks);
    discovery_begin(&s_discovery);one();assert(accepted==1&&s_discovery.cursor==1&&discovery_finished(&s_discovery));assert(!live);
    unsigned total=allocations;
    for(unsigned i=1;i<=total;i++){discovery_reset(&s_discovery);discovery_begin(&s_discovery);allocations=0;fail_at=i;accepted=0;one();assert(!accepted&&s_discovery.failed&&!s_discovery.cursor&&!live);}
    fail_at=0;allocations=0;accepted=0;discovery_reset(&s_discovery);discovery_begin(&s_discovery);
    discovery_publish_entity("event","power","Power","fixture/event/power",NULL,NULL,NULL,NULL);
    assert(accepted==1&&s_discovery.cursor==1&&!live);total=allocations;
    for(unsigned i=1;i<=total;i++){
      discovery_reset(&s_discovery);discovery_begin(&s_discovery);allocations=0;fail_at=i;accepted=0;
      discovery_publish_entity("event","power","Power","fixture/event/power",NULL,NULL,NULL,NULL);
      assert(!accepted&&s_discovery.failed&&!s_discovery.cursor&&!live);
    }
    fail_at=0;accepted=0;discovery_reset(&s_discovery);
    unsigned passes=0;
    while(s_discovery.cursor<100){
        discovery_begin(&s_discovery);unsigned before=accepted;
        for(unsigned i=0;i<100;i++)if(discovery_visit(&s_discovery)){accepted++;discovery_result(&s_discovery,true);}
        assert(accepted-before<=4);passes++;
    }
    assert(passes==25&&accepted==100&&discovery_finished(&s_discovery));
    discovery_reset(&s_discovery);discovery_begin(&s_discovery);publish_result=-2;one();assert(!s_discovery.cursor&&s_discovery.failed);
    discovery_begin(&s_discovery);publish_result=1;one();assert(s_discovery.cursor==1&&!s_discovery.failed);
    assert(!live);cJSON_InitHooks(NULL);
    puts("PASS: actual HA entity serializer every-allocation refusal, bounded four-entity batches, cursor retention on full outbox (mock MQTT)");
}
'''
with tempfile.TemporaryDirectory(prefix='mqtt-discovery-') as folder:
    p=Path(folder);(p/'test.c').write_text(PROGRAM+src+TAIL);binary=p/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'main')];libs=[]
    cjson=os.environ.get('CJSON_SOURCE')
    if cjson:flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('DISCOVERY_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
