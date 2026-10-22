"""Actual LAN -> Tailnet destination-check core with fixture rules/path/socket.

Covers request validation, identity binding, single pending slot, cooldown,
clock regression, UDP honesty, control/authority/resolution/resource gates,
rule change while queued and stale publication. No device or network I/O.
Set SC_SANITIZE=1 on Linux to add ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
def between(path, start, end):
    text = (ROOT / path).read_text(encoding='utf-8')
    return start + text.split(start, 1)[1].split(end, 1)[0]

forward = between('main/tailnet_forward.h', '#define TAILNET_FORWARD_MAX', 'typedef struct {\n    bool installed;')
header = between('main/service_check.h', 'typedef enum {', '/* ESP_ERR_INVALID_ARG')
core = between('main/service_check.c', '/* --- service check core (begin) --- */', '/* --- service check core (end) --- */')

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_TIMEOUT 0x107
#define ESP_ERR_NOT_FINISHED 0x10c
''' + forward + header + r'''
typedef struct {bool ready, connected, authority; uint32_t resolved_ip;} sc_path_t;
static uint64_t now; static tailnet_forward_rule_t rules[TAILNET_FORWARD_MAX]; static bool present[TAILNET_FORWARD_MAX];
static sc_path_t path; static int connect_result=1, connects; static bool admit=true; static uint32_t last_ip; static uint16_t last_port;
static int edit_during_connect=-1;
static uint64_t sc_now_ms(void){return now;}
static bool sc_rule(int i,tailnet_forward_rule_t *r){if(i<0||i>=TAILNET_FORWARD_MAX||!present[i])return false;*r=rules[i];return true;}
static void sc_path(const tailnet_forward_rule_t *r,sc_path_t *out){(void)r;*out=path;}
static void sc_run(void);
static int sc_connect(uint32_t ip,uint16_t port,uint32_t timeout){
    assert(timeout==SERVICE_CHECK_TIMEOUT_MS);connects++;last_ip=ip;last_port=port;now+=37;
    if(edit_during_connect>=0){rules[edit_during_connect].destination_port++;edit_during_connect=-1;}
    return connect_result;}
static bool sc_admit(void){return admit;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){
    uint32_t h=2166136261u;const uint8_t *p=(const uint8_t*)r->destination;for(size_t i=0;i<sizeof r->destination;i++)h=(h^p[i])*16777619u;
    h=(h^r->destination_port)*16777619u;h=(h^r->proto)*16777619u;h=(h^r->listen_port)*16777619u;return h;}
#define SC_LOCK() ((void)0)
#define SC_UNLOCK() ((void)0)
''' + core + r'''
static uint32_t token(int i){return service_lease_token(&rules[i]);}
static service_check_result_t got(int i){service_check_result_t r={0};assert(sc_get_locked(i,token(i),&r));return r;}
int main(void){
    for(int i=0;i<3;i++){present[i]=true;rules[i].valid=1;rules[i].proto=TAILNET_FORWARD_PROTO_TCP;rules[i].listen_port=8000+i;rules[i].destination_port=443;
        snprintf(rules[i].destination,sizeof rules[i].destination,"nas-%d",i);}
    rules[2].proto=TAILNET_FORWARD_PROTO_UDP;
    path=(sc_path_t){.connected=true,.authority=true,.resolved_ip=0x64400001u};now=1000;
    service_check_result_t r;
    assert(sc_request_locked(-1,1,now)==ESP_ERR_INVALID_ARG&&sc_request_locked(TAILNET_FORWARD_MAX,1,now)==ESP_ERR_INVALID_ARG);
    assert(sc_request_locked(5,1,now)==ESP_ERR_INVALID_ARG); /* empty slot */
    assert(sc_request_locked(0,0,now)==ESP_ERR_INVALID_STATE&&sc_request_locked(0,token(0)^1,now)==ESP_ERR_INVALID_STATE);
    assert(!sc_get_locked(0,token(0),&r)&&!sc_get_locked(0,0,&r)&&!sc_get_locked(99,1,&r));
    for(unsigned s=0;s<SC_STATE_COUNT;s++)assert(service_check_state_name(s)[0]&&service_check_summary(s)[0]&&service_check_next_step(s)[0]);
    assert(!strcmp(service_check_state_name(SC_STATE_COUNT),"unknown"));

    /* Reachable: one connect to the resolved Tailnet IP/port, enabled flag irrelevant. */
    assert(rules[0].enabled==0&&sc_request_locked(0,token(0),now)==ESP_OK);
    assert(got(0).state==SC_PENDING&&!got(0).observed_ms);
    assert(sc_request_locked(1,token(1),now)==ESP_ERR_NOT_FINISHED); /* single pending slot */
    sc_run();r=got(0);assert(r.state==SC_REACHABLE&&connects==1&&last_ip==0x64400001u&&last_port==443&&r.latency_ms==37&&r.observed_ms==1037);
    sc_run();assert(connects==1); /* nothing pending: no I/O */
    /* Cooldown per identity; clock regression does not lock the rule out. */
    assert(sc_request_locked(0,token(0),now+SERVICE_CHECK_COOLDOWN_MS-1)==ESP_ERR_TIMEOUT);
    assert(sc_request_locked(0,token(0),now+SERVICE_CHECK_COOLDOWN_MS)==ESP_OK);
    connect_result=0;sc_run();assert(got(0).state==SC_NO_ANSWER);
    connect_result=-1;assert(sc_request_locked(0,token(0),5)==ESP_OK);sc_run();assert(got(0).state==SC_LOCAL_ERROR);connect_result=1;

    /* Editing the rule hides old evidence (new identity has no result). */
    rules[0].destination_port=8443;assert(!sc_get_locked(0,token(0),&r));rules[0].destination_port=443;
    assert(sc_get_locked(0,token(0),&r)&&r.state==SC_LOCAL_ERROR);

    /* UDP never connects and never claims reachability. */
    now+=10000;int before=connects;assert(sc_request_locked(2,token(2),now)==ESP_OK);sc_run();
    assert(got(2).state==SC_UDP_UNVERIFIABLE&&connects==before);

    /* Gates in order: control, authority, resolution, admission. */
    struct {sc_path_t p;bool admit;uint8_t want;} gates[]={
        {{.connected=false,.authority=true,.resolved_ip=0x64400001u},true,SC_NO_CONTROL},
        {{.connected=true,.authority=false,.resolved_ip=0x64400001u},true,SC_NO_AUTHORITY},
        {{.connected=true,.authority=true,.resolved_ip=0},true,SC_UNRESOLVED},
        {{.connected=true,.authority=true,.resolved_ip=0xc0a80101u},true,SC_UNRESOLVED},
        {{.connected=true,.authority=true,.resolved_ip=0x64400001u},false,SC_RESOURCE}};
    for(unsigned g=0;g<sizeof gates/sizeof gates[0];g++){
        now+=10000;path=gates[g].p;admit=gates[g].admit;before=connects;
        assert(sc_request_locked(1,token(1),now)==ESP_OK);sc_run();r=got(1);
        assert(r.state==gates[g].want&&connects==before);
        if(r.state==SC_UNRESOLVED)assert(!r.resolved_ip);
    }
    path=(sc_path_t){.connected=true,.authority=true,.resolved_ip=0x64400002u};admit=true;

    /* Rule changed or removed while queued: nothing tested. */
    now+=10000;uint32_t queued=token(1);assert(sc_request_locked(1,queued,now)==ESP_OK);
    rules[1].destination_port=22;before=connects;sc_run();
    assert(connects==before&&sc_get_locked(1,queued,&r)&&r.state==SC_CHANGED&&!sc_get_locked(1,token(1),&r));
    now+=10000;assert(sc_request_locked(1,token(1),now)==ESP_OK);present[1]=false;sc_run();
    assert(sc_results[1].state==SC_CHANGED&&!sc_pending.active);present[1]=true;
    /* Edit during the connect: the result is bound to the tested identity only. */
    now+=10000;queued=token(0);edit_during_connect=0;assert(sc_request_locked(0,queued,now)==ESP_OK);sc_run();
    assert(sc_get_locked(0,queued,&r)&&r.state==SC_REACHABLE&&!sc_get_locked(0,token(0),&r));
    /* Zero clock still publishes a nonzero observation time. */
    now=0;rules[0].destination_port=443;assert(sc_request_locked(1,token(1),0)==ESP_OK);
    path.connected=false;sc_run();assert(got(1).observed_ms==1&&!sc_pending.active);
    puts("PASS: actual destination check: validation, identity binding, single slot, cooldown/clock, UDP honesty, gates, queued edits (fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='service-check-') as folder:
    p = Path(folder); (p / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = p / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get('SC_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(p / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
