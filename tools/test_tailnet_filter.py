"""Run actual Tailnet forwarding filters on synthetic raw/Ethernet packets.

No device/network access. TAILNET_SANITIZE=1 enables ASan/UBSan in CI.
This tests destination/source policy and chained-pbuf parsing, not the SDK's
NAPT implementation or end-to-end fragment forwarding.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/'main/tailnet_forward.c').read_text(encoding='utf-8')
filter_functions = 'static bool packet_fields' + source.split('static bool packet_fields', 1)[1]
conflicts = 'bool tailnet_forward_listen_conflicts' + source.split(
    'bool tailnet_forward_listen_conflicts', 1)[1].split('esp_err_t tailnet_forward_set_all', 1)[0]
policy='int tailnet_forward_snapshot_mappings'+source.split('int tailnet_forward_snapshot_mappings',1)[1].split('static bool packet_fields',1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef int esp_err_t;
#include "tailnet_forward.h"
static uint64_t s_generation=1;
typedef struct { bool installed; tailnet_forward_mapping_t mapping; } active_mapping_t;
static active_mapping_t s_active[TAILNET_FORWARD_MAX];
static tailnet_forward_rule_t s_rules[TAILNET_FORWARD_MAX];
static tailnet_forward_runtime_t s_runtime[TAILNET_FORWARD_MAX];
static int s_count, lock_depth;
#define LOCK() do { assert(!lock_depth); ++lock_depth; } while(0)
#define UNLOCK() do { assert(lock_depth==1); --lock_depth; } while(0)
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define lwip_htonl swap32
#define netif_ip4_addr(n) (&(n)->ip)
static size_t strlcpy(char *d,const char *s,size_t z) { size_t n=strlen(s);if(z){size_t c=n<z-1?n:z-1;memcpy(d,s,c);d[c]=0;}return n; }
#define lwip_ntohs(x) ((uint16_t)(((x)>>8)|((x)<<8)))
struct ip_hdr { uint8_t vhl,tos; uint16_t len,id,offset; uint8_t ttl,proto; uint16_t sum; struct { uint32_t addr; } src,dest; };
#define IPH_V(i) ((i)->vhl>>4)
#define IPH_HL(i) ((i)->vhl&15)
#define IPH_OFFSET(i) ((i)->offset)
#define IPH_PROTO(i) ((i)->proto)
#define IP_OFFMASK 0x1fff
static uint16_t pbuf_copy_partial(const struct pbuf *p,void *to,uint16_t length,uint16_t offset) {
    uint16_t copied=0;
    while(p && copied<length) {
        if(offset>=p->len) { offset-=p->len; p=p->next; continue; }
        uint16_t n=p->len-offset; if(n>length-copied)n=length-copied;
        memcpy((uint8_t*)to+copied,(uint8_t*)p->payload+offset,n);
        copied+=n; offset=0; p=p->next;
    }
    return copied;
}
static const uint32_t local_hbo=0xc0000201;
#define ALLOW_UP(p) tailnet_forward_allow_uplink_packet(p,swap32(local_hbo))
#define ALLOW_OTHER(p,eth) tailnet_forward_allow_non_uplink_packet(p,eth,swap32(local_hbo))
static void packet(uint8_t *b,bool eth,uint8_t proto,uint32_t src,uint32_t dest,uint16_t port) {
    memset(b,0,80); size_t off=eth?14:0;
    if(eth) { b[12]=8; b[13]=0; }
    b[off]=0x45; b[off+3]=40; b[off+8]=64; b[off+9]=proto;
    uint32_t n=swap32(src); memcpy(b+off+12,&n,4); n=swap32(dest); memcpy(b+off+16,&n,4);
    b[off+22]=port>>8; b[off+23]=port;
}
'''
tests = r'''
static void install(void) {
    tailnet_forward_mapping_t maps[TAILNET_FORWARD_MAX];
    int count=tailnet_forward_snapshot_mappings(maps,TAILNET_FORWARD_MAX);
    tailnet_forward_prepare_install();
    for(int i=0;i<count;i++){maps[i].binding_ip_nbo=swap32(local_hbo);tailnet_forward_mark_installed(&maps[i],true,NULL);}
}
int main(void) {
    s_count=1;
    s_rules[0]=(tailnet_forward_rule_t){.valid=1,.enabled=1,.proto=6,.listen_port=2222,.destination_port=22,.source_network=0xc0000200,.source_prefix=24};
    s_runtime[0].installed=true; s_runtime[0].resolved_ip=0x64400002;
    install();
    uint8_t bytes[80]; struct pbuf p={.payload=bytes,.len=54,.tot_len=54};
    /* A same-numbered service on another host is not our forwarding listener. */
    packet(bytes,true,6,0xc6336402,0xc0000202,2222);
    assert(ALLOW_UP(&p) && s_runtime[0].blocked_packets==0);
    packet(bytes,true,6,0xc6336402,local_hbo,2222); assert(!ALLOW_UP(&p));
    packet(bytes,true,6,0xc0000263,local_hbo,2222); assert(ALLOW_UP(&p));
    assert(s_runtime[0].blocked_packets==1 && s_runtime[0].accepted_packets==1);
    tailnet_forward_prepare_install(); assert(ALLOW_UP(&p)); install();
    for(unsigned prefix=0;prefix<=32;prefix++) {
        uint32_t mask=prefix==0?0:(prefix==32?UINT32_MAX:UINT32_MAX<<(32-prefix));
        s_rules[0].source_prefix=prefix; s_rules[0].source_network=0xc0000263&mask;
        install();
        assert(ALLOW_UP(&p));
    }
    s_rules[0].source_prefix=24; s_rules[0].source_network=0xc0000200;
    s_rules[0].source_prefix=33; install(); assert(!ALLOW_UP(&p)); s_rules[0].source_prefix=24; install();
    /* Deny equivalent local listener access from AP and tunnel inputs,
     * but do not interfere with routed/AP-subnet traffic to other hosts. */
    for(unsigned eth=0;eth<2;eth++) {
        p.len=p.tot_len=eth?54:40;
        packet(bytes,eth,6,0xc0000263,local_hbo,2222); assert(!ALLOW_OTHER(&p,eth));
        packet(bytes,eth,6,0xc0000263,0xc0000202,2222); assert(ALLOW_OTHER(&p,eth));
        packet(bytes,eth,6,0xc0000263,local_hbo,3333); assert(ALLOW_OTHER(&p,eth));
    }
    p.len=p.tot_len=54;
    /* The policy must not depend on where a pbuf chain splits the header. */
    packet(bytes,true,6,0xc6336402,local_hbo,2222);
    for(unsigned split=1;split<54;split++) {
        struct pbuf second={.payload=bytes+split,.len=54-split,.tot_len=54-split};
        struct pbuf first={.next=&second,.payload=bytes,.len=split,.tot_len=54};
        assert(!ALLOW_UP(&first));
    }
    s_rules[0].proto=17; install(); packet(bytes,true,17,0xc6336402,local_hbo,2222); assert(!ALLOW_UP(&p));
    s_rules[0].enabled=0; install(); assert(ALLOW_UP(&p)); s_rules[0].enabled=1; install();
    packet(bytes,true,6,0xc6336402,local_hbo,2222); assert(ALLOW_UP(&p));
    assert(!lock_depth);
    /* Malformed/header-boundary coverage; sanitizers catch invalid reads. */
    uint32_t rng=21;
    for(unsigned i=0;i<50000;i++) {
        for(unsigned j=0;j<80;j++) { rng=rng*1664525u+1013904223u; bytes[j]=rng>>24; }
        p.len=p.tot_len=rng%81; (void)ALLOW_UP(&p); (void)ALLOW_OTHER(&p,false);
    }
    assert(pbuf_copy_partial(&p,bytes,0,0)==0);
    puts("PASS: actual Tailnet filter scopes listener policy to local destination, source masks 0..32, installed/disabled/protocol behavior, raw/Ethernet traffic, 53 pbuf splits and 50000 malformed packets");
}
'''
with tempfile.TemporaryDirectory(prefix='tailnet-filter-') as directory:
    path=Path(directory)
    (path/'lwip').mkdir()
    (path/'lwip/pbuf.h').write_text('#pragma once\nstruct pbuf { struct pbuf *next; void *payload; unsigned short len,tot_len; };\n', encoding='utf-8')
    (path/'lwip/netif.h').write_text('#pragma once\nstruct netif { char name[2]; unsigned char napt; struct { unsigned addr; } ip; };\n',encoding='utf-8')
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n', encoding='utf-8')
    (path/'test.c').write_text(fixture+conflicts+policy+filter_functions+tests, encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror']
    if os.environ.get('TAILNET_SANITIZE')=='1': flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,'-I',str(path),'-I',str(ROOT/'main'),str(path/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
