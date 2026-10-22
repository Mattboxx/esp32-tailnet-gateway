"""Compile and exercise the real SNMP codec/PDU functions with synthetic MIBs,
then the real MIB table, ordering, lookups and operational snapshot cache.

No device access. Set SNMP_SANITIZE=1 on Linux to add ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "components/snmp_agent/snmp_agent.c").read_text(encoding="utf-8")

def section(start, end):
    return source.split(start, 1)[1].split(end, 1)[0]

constants = section('#define PKT_BUF', '/* ------------------------------------------------------------------ */')
constants = '#define PKT_BUF' + constants
buffers = section('typedef struct {\n    uint8_t rx[PKT_BUF];', '} snmp_buffers_t;')
buffers = 'typedef struct {\n    uint8_t rx[PKT_BUF];' + buffers + '} snmp_buffers_t;\n'
codec = 'static int ber_put_len' + section('static int ber_put_len', '/* OID table')
parser = 'static int process_pdu' + section('static int process_pdu', '/* SNMP task')

fixture = r'''
typedef struct { uint32_t arc[MAX_OID]; int n; } oid_t;
static const struct { oid_t oid; } s_mib[] = {{{{1,3,6,1,2,1,1,1,0},9}}};
static int mib_get(const uint32_t *arc, int n) {
    return n == 9 && !memcmp(arc, s_mib[0].oid.arc, 9*sizeof(*arc)) ? 0 : -1;
}
static int mib_getnext(const uint32_t *arc, int n) {
    for(int i=0;i<n && i<9;i++) {
        if(arc[i] < s_mib[0].oid.arc[i]) return 0;
        if(arc[i] > s_mib[0].oid.arc[i]) return -1;
    }
    return n < 9 ? 0 : -1;
}
static int encode_val(uint8_t *b, int cap, int row) {
    (void)row; char str[256]; memset(str,'x',255); str[255]=0;
    return ber_enc_str(b,cap,str);
}
'''
tests = r'''
static int wrap(uint8_t *out, uint8_t tag, const uint8_t *in, int n) {
    uint8_t header[4]; int h=seq_hdr(header,4,tag,n);
    memcpy(out,header,h); memcpy(out+h,in,n); return h+n;
}
static int make_request(uint8_t *out, int version, int tag, const char *comm, int ridlen) {
    uint8_t oid[128], vb[160], vbl[180], pdu[300], body[600], message[700];
    int a=ber_enc_oid(oid,sizeof oid,s_mib[0].oid.arc,9);
    oid[a++]=5; oid[a++]=0;
    a=wrap(vb,0x30,oid,a); a=wrap(vbl,0x30,vb,a);
    int p=0; pdu[p++]=2; pdu[p++]=ridlen;
    for(int i=0;i<ridlen;i++) pdu[p++]=1;
    for(int i=0;i<2;i++) {pdu[p++]=2;pdu[p++]=1;pdu[p++]=0;}
    memcpy(pdu+p,vbl,a);p+=a;
    p=wrap(message,tag,pdu,p);
    int b=0;body[b++]=2;body[b++]=1;body[b++]=version;
    b+=ber_enc_str(body+b,sizeof body-b,comm);
    memcpy(body+b,message,p);b+=p;
    return wrap(out,0x30,body,b);
}
int main(void) {
    snmp_buffers_t *buffers=calloc(1,sizeof(*buffers)); assert(buffers);
    uint8_t in[PKT_BUF], out[PKT_BUF+16];
    int n=make_request(in,1,0xa0,"fixture",1);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)>255);
    assert(process_pdu(in,n,out,16,"fixture",buffers)<0);
    assert(process_pdu(in,n,out,PKT_BUF,"wrong",buffers)<0);
    for(int i=0;i<n;i++) assert(process_pdu(in,i,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,0,0xa1,"fixture",4);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)>0);
    n=make_request(in,3,0xa0,"fixture",1);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa3,"fixture",1); /* SET must never be answered */
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa0,"fixture",0);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa0,"fixture",8);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    uint32_t arc[MAX_OID]; int count;
    const uint8_t bad_oid[]={43,0xff,0xff,0xff,0xff,0xff,0x7f};
    assert(!ber_dec_oid(bad_oid,sizeof bad_oid,arc,&count,MAX_OID));
    uint32_t rng=1234567;
    for(int iteration=0;iteration<50000;iteration++) {
        n=make_request(in,1,0xa0,"fixture",1);
        if(iteration%2) {
            rng=rng*1664525u+1013904223u; n=rng%PKT_BUF;
            for(int i=0;i<n;i++) {rng=rng*1664525u+1013904223u;in[i]=rng>>24;}
        } else {
            rng=rng*1664525u+1013904223u; int at=rng%n;
            rng=rng*1664525u+1013904223u; in[at]=rng>>24;
        }
        memset(out,0xa5,sizeof out);
        int reply=process_pdu(in,n,out,PKT_BUF,"fixture",buffers);
        assert(reply<=PKT_BUF);
        for(int i=PKT_BUF;i<(int)sizeof out;i++) assert(out[i]==0xa5);
    }
    free(buffers);puts("PASS: SNMP v1/v2c, wrong community, SET rejection, truncation, lengths, OID overflow, 50000 malformed/mutated packets");
}
'''
HEADER = '#define _POSIX_C_SOURCE 200809L\n#include <stdint.h>\n#include <stdbool.h>\n#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <assert.h>\n'
program = HEADER + constants + buffers + codec + fixture + parser + tests

# Second program: the actual s_mib table, lookup/encode functions and the
# operational snapshot block. Unrelated device getters become zero stubs.
import re
operational_h = (ROOT / "components/snmp_agent/include/snmp_operational.h").read_text(encoding="utf-8")
operational_h = operational_h.replace('#pragma once', '')
OID_TYPE = 'typedef struct { uint32_t arc[MAX_OID]; int n; } oid_t;'
types = OID_TYPE + section(OID_TYPE, '/* --- system group --- */')
ops = '/* --- operational snapshot (begin) --- */' + section('/* --- operational snapshot (begin) --- */', '/* --- operational snapshot (end) --- */')
table = 'static const mib_row_t s_mib[] = {' + section('static const mib_row_t s_mib[] = {', '#define MIB_LEN')
lookup = '#define MIB_LEN' + section('#define MIB_LEN', '/* ------------------------------------------------------------------ */')
stubs = ''.join('static val_t %s(void){return (val_t){.u=0};}\n' % name
                for name in sorted(set(re.findall(r'\b(g_\w+)\}', table))) if not name.startswith('g_ops_'))
ops_tests = r'''
static int64_t fake_now; static int calls; static uint32_t seed;
static int64_t esp_timer_get_time(void){return fake_now;}
static void provider_a(snmp_operational_metrics_t *out){
    calls++; out->value[SNMP_OPS_AVAILABLE]=1;
    for(unsigned i=2;i<SNMP_OPS_LIMIT;i++) out->value[i]=seed+i;
}
static void provider_b(snmp_operational_metrics_t *out){calls++;out->value[SNMP_OPS_AVAILABLE]=1;out->value[SNMP_OPS_RESET_REASON]=7;}
static int row_of(unsigned metric){uint32_t arc[]={1,3,6,1,4,1,99999,2,metric,0};return mib_get(arc,10);}
int main(void){
    for(int i=1;i<MIB_LEN;i++) assert(oid_cmp(s_mib[i-1].oid.arc,s_mib[i-1].oid.n,s_mib[i].oid.arc,s_mib[i].oid.n)<0);
    uint32_t start[]={1,3}; int visited=0;
    for(int row=mib_getnext(start,2);row>=0;row=mib_getnext(s_mib[row].oid.arc,s_mib[row].oid.n)) visited++;
    assert(visited==MIB_LEN);
    uint32_t heap[]={1,3,6,1,4,1,99999,1,1,4,0};
    int first=mib_getnext(heap,11); assert(first==row_of(1)&&first>0);
    for(unsigned m=1;m<SNMP_OPS_LIMIT;m++){int r=row_of(m);assert(r>=0&&s_mib[r].vt==VT_GAUGE32);}
    assert(row_of(0)<0&&row_of(SNMP_OPS_LIMIT)<0);
    uint32_t last[]={1,3,6,1,4,1,99999,2,SNMP_OPS_LIMIT-1,0};assert(mib_getnext(last,10)==-1);
    uint32_t prefix[]={1,3,6,1,4,1,99999,2};assert(mib_getnext(prefix,8)==row_of(1));
    /* No provider: honest unavailable, every value zero. */
    for(unsigned m=1;m<SNMP_OPS_LIMIT;m++) assert(ops_metric(m)==0);
    assert(ops_metric(0)==0&&ops_metric(SNMP_OPS_LIMIT)==0&&ops_metric(1000)==0);
    /* Registration is visible after the one-second cache window only. */
    snmp_agent_set_operational_provider(provider_a); seed=100;
    assert(ops_metric(SNMP_OPS_AVAILABLE)==0&&calls==0);
    fake_now=1000000; assert(ops_metric(SNMP_OPS_AVAILABLE)==1&&calls==1);
    for(unsigned m=2;m<SNMP_OPS_LIMIT;m++) assert(ops_metric(m)==100+m);
    assert(calls==1); /* a full walk costs one provider call */
    uint8_t b[32]; int n=encode_val(b,sizeof b,row_of(SNMP_OPS_RESET_REASON));
    assert(n>=3&&b[0]==0x42&&b[n-1]==100+SNMP_OPS_RESET_REASON);
    assert(encode_val(b,1,row_of(SNMP_OPS_RESET_REASON))<=0);
    seed=200; fake_now=1999999; assert(ops_metric(5)==105&&calls==1);
    fake_now=2000000; assert(ops_metric(5)==205&&calls==2);
    /* Clock moving backwards refreshes instead of freezing stale values. */
    seed=300; fake_now=10; assert(ops_metric(5)==305&&calls==3);
    /* A replacement provider never inherits values the old one set. */
    snmp_agent_set_operational_provider(provider_b); fake_now=2000000;
    assert(ops_metric(5)==0&&ops_metric(SNMP_OPS_RESET_REASON)==7&&calls==4);
    snmp_agent_set_operational_provider(NULL); fake_now=4000000;
    assert(ops_metric(SNMP_OPS_AVAILABLE)==0&&ops_metric(SNMP_OPS_RESET_REASON)==0&&calls==4);
    puts("PASS: actual MIB order/walk/lookups, 27 operational Gauge32 rows, unavailable default, 1 s cache, clock regression, provider replacement");
}
'''
mib_program = (HEADER + '#include <stdatomic.h>\n' + constants + operational_h + types + codec
               + 'static int64_t esp_timer_get_time(void);\n' + stubs + ops + table + lookup + ops_tests)

with tempfile.TemporaryDirectory(prefix="snmp-codec-") as directory:
    path = Path(directory)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get("SNMP_SANITIZE") == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    for stem, text in (('test', program), ('mib', mib_program)):
        (path / (stem + '.c')).write_text(text, encoding="utf-8")
        binary = path / (stem + ('.exe' if os.name == 'nt' else ''))
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path/(stem + '.c')), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

# Third program: the actual operational provider (main/snmp_ops.c) against
# fixture modules, including Service Gateway evidence counting.
ops_header = (ROOT / 'main/homelab_ops.h').read_text(encoding='utf-8')
resources = 'typedef struct {\n    uint32_t internal_free' + ops_header.split('typedef struct {\n    uint32_t internal_free', 1)[1].split('} ops_resources_t;', 1)[0] + '} ops_resources_t;\n'
provider = (ROOT / 'main/snmp_ops.c').read_text(encoding='utf-8')
provider = 'static void operational_metrics' + provider.split('static void operational_metrics', 1)[1]
PROVIDER_TEST = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "snmp_operational.h"
#include "service_evidence.h"
''' + resources + r'''
static int rows=3;static tailnet_forward_rule_t rules[3];static tailnet_forward_runtime_t rts[3];
static uint8_t check_state[3]={SC_REACHABLE,SC_NO_ANSWER,SC_REACHABLE};static bool check_present[3]={true,true,false};static bool reply[3]={true,false,true};
static void homelab_ops_resources(ops_resources_t *r){memset(r,0,sizeof *r);r->internal_free=1000;r->internal_largest=900;r->sockets_used=5;r->socket_limit=16;r->worker_running=false;r->worker_stack_min=77;}
void ml_policy_get_status(ml_policy_status_t *p){memset(p,0,sizeof *p);p->authority_ready=true;p->peers=4;p->return_flows=2;}
void tailnet_forward_totals(uint32_t *e,uint32_t *n,uint32_t *a,uint32_t *b){*e=2;*n=1;*a=40;*b=3;}
bool tailnet_forward_get(int i,tailnet_forward_rule_t *r,tailnet_forward_runtime_t *rt){if(i<0||i>=rows)return false;*r=rules[i];*rt=rts[i];return true;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){return r->listen_port+1u;}
bool service_check_get(int i,uint32_t t,service_check_result_t *out){if(!check_present[i])return false;*out=(service_check_result_t){.state=check_state[i],.token=t};return true;}
bool ml_policy_reply_age(uint8_t p,const uint8_t ip[4],uint16_t port,uint32_t *age){(void)p;(void)port;*age=1000;return reply[ip[3]-1];}
static bool mqtt_integration_connected(void){return true;}
static bool tailscale_is_connected(void){return false;}
static int esp_reset_reason(void){return 3;}
static snmp_operational_provider_t registered;
void snmp_agent_set_operational_provider(snmp_operational_provider_t p){registered=p;}
static void health_monitor_codes(uint8_t out[4]){out[0]=3;out[1]=5;out[2]=1;out[3]=8;}
''' + provider + r'''
int main(void){
    for(int i=0;i<3;i++){rules[i]=(tailnet_forward_rule_t){.valid=1,.proto=6,.listen_port=(uint16_t)(1000+i)};rts[i]=(tailnet_forward_runtime_t){.resolved_ip=0x64400001u+i};}
    homelab_snmp_register();assert(registered);
    snmp_operational_metrics_t m;memset(&m,0xa5,sizeof m);registered(&m);
    assert(m.value[0]==0&&m.value[SNMP_OPS_AVAILABLE]==1&&m.value[SNMP_OPS_INTERNAL_FREE]==1000&&m.value[SNMP_OPS_SOCKETS_USED]==5);
    assert(m.value[SNMP_OPS_WORKER_STACK_RAW]==UINT32_MAX); /* not running: not-applicable sentinel, never a fake 0 */
    assert(m.value[SNMP_OPS_POLICY_PEERS]==4&&m.value[SNMP_OPS_FORWARD_ACCEPTED]==40&&m.value[SNMP_OPS_CONTROL_CONNECTED]==0&&m.value[SNMP_OPS_RESET_REASON]==3);
    assert(m.value[SNMP_OPS_FORWARD_REACHABLE]==1); /* rule 2 has no current test */
    assert(m.value[SNMP_OPS_FORWARD_REPLIED]==2);
    assert(m.value[SNMP_OPS_HEALTH_GATEWAY]==3&&m.value[SNMP_OPS_HEALTH_DNS]==5&&m.value[SNMP_OPS_HEALTH_INTERNET]==1&&m.value[SNMP_OPS_HEALTH_TAILNET]==8);
    rts[2].resolved_ip=0;registered(&m);assert(m.value[SNMP_OPS_FORWARD_REPLIED]==1); /* unresolved: no reply query */
    rows=0;registered(&m);assert(!m.value[SNMP_OPS_FORWARD_REACHABLE]&&!m.value[SNMP_OPS_FORWARD_REPLIED]);
    puts("PASS: actual SNMP operational provider: resource/policy/forwarding values, not-running sentinel, Service Gateway reachable/replied counts (fixtures)");
}
'''
PSTUBS = {'esp_err.h': '#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n', 'lwip/pbuf.h': '#pragma once\nstruct pbuf;\n', 'lwip/netif.h': '#pragma once\nstruct netif;\n'}
with tempfile.TemporaryDirectory(prefix="snmp-provider-") as directory:
    path = Path(directory); (path / 'lwip').mkdir()
    for name, text in PSTUBS.items(): (path / name).write_text(text)
    (path / 'provider.c').write_text(PROVIDER_TEST.replace('#include "snmp_ops.h"\n', '').replace('#include "homelab_ops.h"\n', '')
        .replace('#include "mqtt_integration.h"\n', '').replace('#include "tailscale_config.h"\n', '').replace('#include "service_lease.h"\n', '')
        .replace('#include "esp_system.h"\n', ''), encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main'),
             '-I', str(ROOT / 'components/snmp_agent/include'), '-I', str(ROOT / 'external/microlink/components/microlink/include')]
    dep = os.environ.get('CJSON_SOURCE'); libs = []
    if dep: flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get("SNMP_SANITIZE") == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('provider.exe' if os.name == 'nt' else 'provider')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'provider.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True)
