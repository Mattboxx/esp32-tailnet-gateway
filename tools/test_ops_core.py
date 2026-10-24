"""Actual operational C validation/transaction/transitions, synthetic NVS/time.
No real worker, socket, FreeRTOS, physical NVS or device-recovery claim.
"""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/homelab_ops.c').read_text(encoding='utf-8')
header=(ROOT/'main/homelab_ops.h').read_text(encoding='utf-8')
wol=(ROOT/'main/wol.h').read_text(encoding='utf-8')
def function(name):
    start=source.index(name);return source[start:source.index('\n}',start)+2]+'\n'
types=header[header.index('typedef struct'):header.index('void homelab_ops_init')]
woltype=wol[wol.index('typedef struct'):wol.index('void      wol_init')]
globals=source[source.index('#define OPS_MAGIC'):source.index('static SemaphoreHandle_t lock;')]
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "module_supervisor.h"
#define WOL_MAX_DEVICES 12
#define TAILNET_FORWARD_MAX 8
#define CONFIG_LWIP_MAX_SOCKETS 31
#define ESP_OK 0
#define NVS_READWRITE 1
#define NVS_NAMESPACE "fixture"
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
typedef int esp_err_t,nvs_handle_t;
static unsigned fault,stage,commits;
static int nvs_open(const char *s,int mode,nvs_handle_t *h){(void)s;(void)mode;*h=1;return ++stage==fault?-1:0;}
static int nvs_set_blob(int h,const char *key,const void *v,size_t n){(void)h;(void)key;(void)v;assert(n>0);return ++stage==fault?-1:0;}
static int nvs_commit(int h){(void)h;commits++;return ++stage==fault?-1:0;}
static void nvs_close(int h){(void)h;}
static uint64_t now_ms(void){return 1000;}
static unsigned event_publishes,event_notifies;
static void homelab_ops_init(void){}
static void mqtt_integration_publish_now(void){event_publishes++;}
static bool ntfy_integration_queue_event(const char *s){assert(strstr(s,"temporary service rule(s) closed"));assert(!strstr(s,"100."));event_notifies++;return false;}
'''
body=r'''
int main(void){
    ops_settings_t s={.interval_s=60,.socket_reserve=4};assert(valid_settings(&s));s.monitoring=2;assert(!valid_settings(&s));
    s.monitoring=0;s.lease_notifications=2;assert(!valid_settings(&s));s.lease_notifications=1;assert(valid_settings(&s));
    ops_device_t p={.target="192.0.2.10",.host_port=22,.timeout_s=120,.interval_s=60,.max_checks=20};
    assert(valid_profile(&p));p.host_port=0;assert(!valid_profile(&p));p.host_port=22;
    strcpy(p.target,"http://private.example/");assert(!valid_profile(&p));strcpy(p.target,"peer.example");assert(valid_profile(&p));
    p.max_checks=0;assert(!valid_profile(&p));p.max_checks=20;
    for(unsigned f=1;f<=3;f++){
        memset(&store,0,sizeof store);store.magic=123;ops_store_t candidate={.magic=OPS_MAGIC,.version=1};
        fault=f;stage=0;assert(save_locked(&candidate)!=ESP_OK);assert(store.magic==123);
    }
    ops_store_t candidate={.magic=OPS_MAGIC,.version=1};fault=stage=0;assert(save_locked(&candidate)==ESP_OK);
    assert(store.magic==OPS_MAGIC && store.checksum==checksum(&store));
    homelab_ops_service_closed(1);assert(service_closures==1&&event_publishes==1&&!event_notifies);
    store.settings.lease_notifications=1;homelab_ops_service_closed(2);assert(service_closures==3&&event_notifies==1);
    homelab_ops_service_closed(0);homelab_ops_service_closed(9);assert(service_closures==3);
    store.settings=(ops_settings_t){.guard=0};assert(homelab_ops_admit());
    store.settings=(ops_settings_t){.guard=1,.minimum_internal=100,.minimum_largest=80,.socket_reserve=4};
    resources=(ops_resources_t){.internal_free=100,.internal_largest=80,.sockets_used=26,.socket_limit=31};assert(homelab_ops_admit());
    resources.sockets_used=27;assert(!homelab_ops_admit());resources.sockets_used=26;
    resources.internal_largest=79;assert(!homelab_ops_admit());resources.internal_largest=80;
    resources.internal_free=99;assert(!homelab_ops_admit());assert(denied_jobs==3);
    /* The status probe reports the same decision without counting a denial. */
    assert(homelab_ops_guard_deferring()&&denied_jobs==3);resources.internal_free=100;assert(!homelab_ops_guard_deferring());
    store.settings.guard=0;resources.internal_free=1;assert(!homelab_ops_guard_deferring());store.settings.guard=1;resources.internal_free=100;
    job=(job_t){.id=1,.index=0,.state=J_PRECHECK,.deadline=99999,.manual=true,.wake=true,.profile=p};job_t local=job;
    apply_probe_locked(&local,0,100);assert(job.state==J_WAKE && !job.packet_sent);
    job.state=J_WAIT;local=job;apply_probe_locked(&local,0,100);assert(job.state==J_WAIT && !job.host_seen);
    local=job;apply_probe_locked(&local,1,30);assert(job.state==J_REACHABLE && job.host_seen && !job.service_seen);
    job=(job_t){.id=2,.index=0,.state=J_PRECHECK,.deadline=99999,.manual=true,.profile=p};job.profile.service_port=443;local=job;
    apply_probe_locked(&local,1,25);assert(job.state==J_SERVICE && job.host_seen && !job.service_seen);
    local=job;apply_probe_locked(&local,0,500);assert(job.state==J_SERVICE && !job.service_seen);
    local=job;apply_probe_locked(&local,1,20);assert(job.state==J_REACHABLE && job.service_seen);
    job.state=J_PRECHECK;job.cancel=true;local=job;apply_probe_locked(&local,1,10);assert(job.state==J_CANCELLED);
    job.cancel=false;job.state=J_PRECHECK;local=job;apply_probe_locked(&local,-1,0);assert(job.state==J_UNKNOWN);
    job.state=J_PRECHECK;job.wake=true;job.host_seen=job.service_seen=false;local=job;apply_probe_locked(&local,-1,0);assert(job.state==J_WAKE && !job.service_seen);
    local=job;local.id=999;unsigned checks=job.checks;apply_probe_locked(&local,1,1);assert(job.checks==checks);
    for(unsigned i=0;i<100;i++)event_locked(J_TIMEOUT,0);assert(event_seq>100);
    puts("PASS: actual ops settings/profile bounds, NVS failures/commit, bounded event ring and recovery result transitions (synthetic only)");
}
'''
with tempfile.TemporaryDirectory(prefix='ops-core-') as directory:
    path=Path(directory);program=path/'test.c';binary=path/('test.exe' if os.name=='nt' else 'test')
    adapters='static ops_resources_t resources;\nstatic void homelab_ops_settings(ops_settings_t *out){*out=store.settings;}\nstatic void homelab_ops_resources(ops_resources_t *out){*out=resources;}\n'
    program.write_text(fixture+woltype+types+globals+adapters+''.join(function(n) for n in (
        'static uint32_t checksum(', 'static bool valid_settings(', 'static bool valid_profile(',
        'static void event_locked(', 'static esp_err_t save_locked(', 'void homelab_ops_service_closed(', 'static bool guard_allows(', 'bool homelab_ops_admit(', 'bool homelab_ops_guard_deferring(', 'static void finish_locked(', 'static void apply_probe_locked('))+body,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-misleading-indentation','-g','-I',str(ROOT/'main')]
    if os.environ.get('OPS_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(['gcc',*flags,str(program),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
