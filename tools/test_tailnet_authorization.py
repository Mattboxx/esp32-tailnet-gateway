"""Actual pinned MicroLink policy C, synthetic map/pbuf/clock/transport.

NOT a WireGuard crypto test, physical ESP test, or two-real-client ACL test.
Set POLICY_SANITIZE=1 for ASan/UBSan; POLICY_NO_PIE=1 for affected WSL hosts.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'

HEAD = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include "ml_policy.h"
#include "lwip/pbuf.h"
static _Atomic unsigned allocation_fail;
static _Atomic uint32_t clock_ms=1000;
void *policy_test_alloc(size_t n) {return allocation_fail ? NULL : malloc(n);}
uint32_t policy_test_now(void) {return clock_ms;}
static uint8_t key_a[32]={[31]=1}, key_b[32]={[31]=2};
#define KEY_A "nodekey:0000000000000000000000000000000000000000000000000000000000000001"
#define KEY_B "nodekey:0000000000000000000000000000000000000000000000000000000000000002"
#define NODE "\"Node\":{\"Addresses\":[\"100.64.0.10/32\",\"fd7a:115c:a1e0::10/128\"],\"AllowedIPs\":[\"100.64.0.10/32\",\"192.0.2.0/24\",\"fd7a:115c:a1e0::10/128\",\"fd7a:115c:a1e0:b1a:0:1:c000:200/120\"]}"
#define PEER_A "{\"ID\":1,\"Key\":\"" KEY_A "\",\"Addresses\":[\"100.64.0.1/32\",\"fd7a:115c:a1e0::1/128\"]}"
#define PEER_B "{\"ID\":2,\"Key\":\"" KEY_B "\",\"Addresses\":[\"100.64.0.2/32\",\"fd7a:115c:a1e0::2/128\"]}"
#define PEER_LIST "\"Peers\":[" PEER_A "," PEER_B "]"
#define TCP_RULE "{\"SrcIPs\":[\"100.64.0.1\"],\"IPProto\":[6],\"DstPorts\":[{\"IP\":\"100.64.0.10\",\"Ports\":{\"First\":80,\"Last\":80}}]}"
#define UDP_RULE "{\"SrcIPs\":[\"100.64.0.1\"],\"IPProto\":[17],\"DstPorts\":[{\"IP\":\"192.0.2.0/24\",\"Ports\":{\"First\":53,\"Last\":53}}]}"
#define ALL_RULE "{\"SrcIPs\":[\"*\"],\"DstPorts\":[{\"IP\":\"*\",\"Ports\":{\"First\":0,\"Last\":65535}}]}"
#define FULL "{" NODE "," PEER_LIST ",\"PacketFilter\":[" TCP_RULE "," UDP_RULE "]}"
#define ALL "{" NODE "," PEER_LIST ",\"PacketFilter\":[" ALL_RULE "]}"
static bool apply(const char *s) {
    cJSON *v=cJSON_Parse(s);assert(v);bool ok=ml_policy_apply(v);cJSON_Delete(v);return ok;
}
static struct pbuf packet(unsigned family,unsigned proto,const char *src,const char *dst,unsigned sp,unsigned dp,unsigned flags,unsigned split) {
    static _Thread_local uint8_t bytes[128];
    static _Thread_local struct pbuf tail;
    memset(bytes,0,sizeof bytes);
    unsigned h=family==4?20:40, transport=proto==6?20:8, n=h+transport;
    if (family==4) {
        bytes[0]=0x45;bytes[2]=n>>8;bytes[3]=n;bytes[8]=64;bytes[9]=proto;
        uint8_t unused;assert(ip_parse(src,bytes+12,&unused));assert(ip_parse(dst,bytes+16,&unused));
    } else {
        bytes[0]=0x60;bytes[4]=transport>>8;bytes[5]=transport;bytes[6]=proto;bytes[7]=64;
        uint8_t unused;assert(ip_parse(src,bytes+8,&unused));assert(ip_parse(dst,bytes+24,&unused));
    }
    bytes[h]=sp>>8;bytes[h+1]=sp;bytes[h+2]=dp>>8;bytes[h+3]=dp;
    if(proto==6){bytes[h+12]=0x50;bytes[h+13]=flags;}
    if(proto==17){bytes[h+4]=transport>>8;bytes[h+5]=transport;}
    if(proto==1||proto==58){bytes[h]=flags;bytes[h+1]=0;bytes[h+4]=sp>>8;bytes[h+5]=sp;}
    struct pbuf p={.payload=bytes,.tot_len=n,.len=n};
    if(split && split<n){tail=(struct pbuf){.payload=bytes+split,.tot_len=n-split,.len=n-split};p.next=&tail;p.len=split;}
    return p;
}
static bool rx(unsigned family,unsigned proto,const char *src,const char *dst,unsigned sp,unsigned dp,unsigned flags,const uint8_t key[32]) {
    struct pbuf p=packet(family,proto,src,dst,sp,dp,flags,0);return ml_policy_rx(&p,key);
}
static void standard(void){ml_policy_reset();assert(apply(FULL));}
'''

BODY = r'''
static void basics(void) {
    ml_policy_reset();
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{" NODE "," PEER_LIST "}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PacketFilter\":null}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    standard();
    for(unsigned split=0;split<40;split++) {
        struct pbuf p=packet(4,6,"100.64.0.1","100.64.0.10",40000,80,2,split);
        assert(ml_policy_rx(&p,key_a));
    }
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,22,2,key_a));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,22,0x10,key_a));
    assert(!rx(4,17,"100.64.0.1","100.64.0.10",40000,80,0,key_a));
    assert(!rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(ml_policy_peer_status(key_b)==1); /* Visibility is not port permission. */
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_b));
    assert(rx(4,17,"100.64.0.1","192.0.2.50",40000,53,0,key_a));
    assert(!rx(4,17,"100.64.0.1","192.0.2.50",40000,54,0,key_a));
    assert(!rx(4,6,"100.64.0.1","192.0.2.50",40000,53,2,key_a));
    assert(apply("{\"KeepAlive\":true}"));
    assert(apply("{\"PacketFilter\":null,\"PacketFilters\":null}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PacketFilter\":[]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply(ALL));
    assert(!rx(4,6,"100.64.0.1","198.51.100.10",40000,80,2,key_a));
    assert(rx(6,6,"fd7a:115c:a1e0::1","fd7a:115c:a1e0::10",40000,80,2,key_a));
    assert(!rx(6,6,"fd7a:115c:a1e0::2","fd7a:115c:a1e0::10",40000,80,2,key_a));
    assert(rx(6,6,"fd7a:115c:a1e0::1","fd7a:115c:a1e0:b1a:0:1:c000:232",40000,22,2,key_a));
    assert(rx(4,1,"100.64.0.1","100.64.0.10",123,0,8,key_a));
    assert(!rx(4,1,"100.64.0.1","100.64.0.10",123,0,3,key_a));
    puts("PASS: missing/null/empty policy, visible-but-unauthorized peer, TCP/UDP ports/protocols, direct/subnet/4via6 original-address checks, pbuf splits");
}
static void deltas(void) {
    standard();
    assert(apply("{\"PacketFilters\":{\"extra\":[" ALL_RULE "]}}"));
    assert(rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PacketFilter\":[]}"));
    assert(rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PacketFilter\":[],\"PacketFilters\":{\"extra\":null}}"));
    assert(!rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PacketFilter\":[" ALL_RULE "],\"PacketFilters\":{\"*\":null,\"limited\":[" TCP_RULE "]}}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(!rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PeersRemoved\":[1]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PeersChanged\":[" PEER_A "]}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"Peers\":[" PEER_B "]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    standard();
    assert(!apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"Key\":\"" KEY_B "\"}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    standard();
    assert(!apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"Key\":\"nodekey:0000000000000000000000000000000000000000000000000000000000000003\"}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    ml_policy_reset();assert(apply("{\"KeepAlive\":true}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PacketFilter\":[" ALL_RULE "]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    puts("PASS: named replacement/deletion/clear, legacy+named ordering, authoritative omission, immediate peer revoke/key rotation independent of WG queue, reconnect incomplete map");
}
static void replies(void) {
    const char *empty="{" NODE "," PEER_LIST ",\"PacketFilter\":[]}";
    assert(apply(empty));
    for(unsigned proto=6;proto<=17;proto+=11) {
        assert(!rx(4,proto,"100.64.0.1","100.64.0.10",22,45000,0x12,key_a));
        struct pbuf out=packet(4,proto,"100.64.0.10","100.64.0.1",45000,22,2,0);
        assert(ml_policy_tx(&out,key_a));ml_policy_sent(&out,key_a);
        assert(rx(4,proto,"100.64.0.1","100.64.0.10",22,45000,0x12,key_a));
        assert(!rx(4,proto,"100.64.0.1","100.64.0.10",23,45000,0x12,key_a));
        assert(!rx(4,proto,"100.64.0.2","100.64.0.10",22,45000,0x12,key_b));
        if(proto==6) assert(!rx(4,proto,"100.64.0.1","100.64.0.10",22,45000,2,key_a));
        clock_ms+=120001;
        assert(!rx(4,proto,"100.64.0.1","100.64.0.10",22,45000,0x12,key_a));
    }
    /* NATed LAN -> Tailnet tuples at the WG boundary, NOT remote service authorization. */
    assert(apply("{\"PacketFilter\":[" TCP_RULE "]}"));
    struct pbuf out=packet(4,6,"100.64.0.10","100.64.0.1",50001,22,2,0);
    assert(ml_policy_tx(&out,key_a));ml_policy_sent(&out,key_a);
    assert(rx(4,6,"100.64.0.1","100.64.0.10",22,50001,0x12,key_a));
    assert(apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"Online\":true,\"Endpoints\":[\"192.0.2.1:1234\"]}]}"));
    assert(apply("{\"PacketFilter\":[" TCP_RULE "]}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",22,50001,0x12,key_a));
    assert(apply("{\"PacketFilter\":[]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",22,50001,0x12,key_a));
    out=packet(4,6,"100.64.0.10","100.64.0.1",50001,22,0x10,0);ml_policy_sent(&out,key_a);
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",22,50001,0x10,key_a));
    for(unsigned i=0;i<40;i++) {
        out=packet(4,17,"100.64.0.10","100.64.0.1",51000+i,53,0,0);ml_policy_sent(&out,key_a);clock_ms++;
    }
    assert(!rx(4,17,"100.64.0.1","100.64.0.10",53,51000,0,key_a));
    assert(rx(4,17,"100.64.0.1","100.64.0.10",53,51039,0,key_a));
    ml_policy_reset();out=packet(4,17,"100.64.0.10","100.64.0.1",51039,53,0,0);
    assert(!ml_policy_tx(&out,key_a));ml_policy_sent(&out,key_a);
    assert(apply(empty));assert(!rx(4,17,"100.64.0.1","100.64.0.10",53,51039,0,key_a));
    puts("PASS: TCP/UDP bounded reverse flows, wrong peer/port and unsolicited SYN denied, timeout/eviction, revocation and reconnect invalidate return state");
}
static void invalid(void) {
    const char *bad[]={
        "{\"PacketFilter\":{}}", "{\"PacketFilters\":[]}",
        "{\"PacketFilter\":[],\"PacketFilter\":[" ALL_RULE "]}",
        "{\"packetfilter\":[]}", "{\"peers\":[]}",
        "{\"PeersChangedPatch\":[{\"NodeID\":1,\"key\":\"" KEY_B "\"}]}",
        "{\"PeersChangedPatch\":[{\"NodeID\":1,\"AllowedIPs\":[]}]}",
        "{\"PacketFilters\":{\"*\":[]}}",
        "{\"PacketFilter\":[{\"SrcIPs\":[\"cap:foo\"],\"DstPorts\":[{\"IP\":\"*\",\"Ports\":{\"First\":0,\"Last\":65535}}]}]}",
        "{\"PacketFilter\":[{\"SrcIPs\":[\"*\"],\"SrcBits\":[0],\"DstPorts\":[]}]}",
        "{\"PacketFilter\":[{\"SrcIPs\":[\"*\"],\"Action\":\"accept\",\"DstPorts\":[]}]}",
        "{\"PeersChanged\":[{\"ID\":1,\"Key\":\"" KEY_A "\",\"AllowedIPs\":[\"0.0.0.0/33\"]}]}",
        "{\"PeersChanged\":[{\"ID\":1,\"Key\":\"" KEY_A "\",\"AllowedIPs\":[\"100.64.0.1/32junk\"]}]}",
        "{\"PeersChanged\":[{\"ID\":1,\"Key\":\"" KEY_A "\",\"KeyExpiry\":\"2040-02-30T00:00:00Z\",\"Addresses\":[]}]}",
        "{\"PeersChangedPatch\":[{\"ID\":1}]}", "{\"Node\":{}}"
    };
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
        standard();assert(!apply(bad[i]));
        assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    }
    standard();allocation_fail=1;assert(!apply("{\"PacketFilter\":[]}"));allocation_fail=0;
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply(ALL));
    for(unsigned i=0;i<100000;i++) {
        struct pbuf p=packet(4,6,"100.64.0.1","100.64.0.10",40000,80,2,0);
        uint8_t *b=p.payload;
        switch(i%5) {
            case 0:b[6]=0x20;break; /* first fragment */
            case 1:b[7]=1;break; /* later fragment */
            case 2:b[0]=0x44;break;
            case 3:b[32]=0x40;break;
            default:p.tot_len=i%39;break;
        }
        assert(!ml_policy_rx(&p,key_a));
    }
    struct pbuf p=packet(6,6,"fd7a:115c:a1e0::1","fd7a:115c:a1e0::10",40000,80,2,0);
    ((uint8_t*)p.payload)[6]=44;assert(!ml_policy_rx(&p,key_a));
    assert(apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"KeyExpiry\":\"2000-01-01T00:00:00Z\"}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"KeyExpiry\":null}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(!apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"KeyExpiry\":\"0001-01-01T00:00:00.999Z\"}]}"));
    puts("PASS: malformed/duplicate/unsupported policy fail closed, PSRAM failure, 100000 malformed/fragment packets, expired key");
}
static void ownership(void) {
    assert(apply(ALL));
    assert(apply("{\"PeersChanged\":[{\"ID\":2,\"Key\":\"" KEY_B "\",\"AllowedIPs\":[\"0.0.0.0/0\"]}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_b));
    assert(!rx(4,6,"100.64.0.99","100.64.0.10",40000,80,2,key_b));
    assert(rx(4,6,"203.0.113.50","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PeersChanged\":[{\"ID\":2,\"Key\":\"" KEY_B "\",\"AllowedIPs\":[]}]}"));
    assert(!rx(4,6,"203.0.113.50","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"PeersChangedPatch\":[{\"NodeID\":1,\"Expired\":true}]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    puts("PASS: longest-prefix ownership, exit route cannot spoof CGNAT identity, empty AllowedIPs and expired peer deny");
}
static void bounds_and_ranges(void) {
    for(unsigned scenario=0;scenario<5;scenario++) {
        assert(apply(ALL));cJSON *map=cJSON_CreateObject();assert(map);
        if(scenario==0) {
            cJSON *groups=cJSON_AddObjectToObject(map,"PacketFilters");
            for(unsigned i=0;i<9;i++){char name[8];snprintf(name,sizeof name,"g%u",i);assert(cJSON_AddArrayToObject(groups,name));}
        } else if(scenario==1) {
            cJSON *rules=cJSON_AddArrayToObject(map,"PacketFilter");
            cJSON *rule=cJSON_Parse(TCP_RULE);assert(rule);cJSON_AddItemToArray(rules,rule);
            cJSON *src=cJSON_GetObjectItemCaseSensitive(rule,"SrcIPs");
            for(unsigned i=0;i<128;i++)cJSON_AddItemToArray(src,cJSON_CreateString("100.64.0.1"));
        } else if(scenario==2) {
            cJSON *peers=cJSON_AddArrayToObject(map,"Peers");
            for(unsigned i=0;i<17;i++)cJSON_AddItemToArray(peers,cJSON_Parse(PEER_A));
        } else if(scenario==3) {
            cJSON *peers=cJSON_AddArrayToObject(map,"PeersChanged"), *peer=cJSON_Parse(PEER_A);
            cJSON_AddItemToArray(peers,peer);cJSON *ips=cJSON_AddArrayToObject(peer,"AllowedIPs");
            for(unsigned i=0;i<17;i++)cJSON_AddItemToArray(ips,cJSON_CreateString("100.64.0.1/32"));
        } else {
            cJSON *groups=cJSON_AddObjectToObject(map,"PacketFilters");char name[65];memset(name,'x',64);name[64]=0;
            assert(cJSON_AddArrayToObject(groups,name));
        }
        assert(!ml_policy_apply(map));cJSON_Delete(map);
        assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    }
    assert(apply(ALL));
    assert(apply("{\"PacketFilters\":{\"*\":null,\"g0\":[],\"g1\":[],\"g2\":[],\"g3\":[],\"g4\":[],\"g5\":[],\"g6\":[],\"g7\":[]}}"));
    assert(apply("{\"PacketFilters\":{\"new\":[" TCP_RULE "],\"g0\":null}}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(apply("{\"PacketFilters\":{\"new\":null,\"g0\":[" TCP_RULE "]}}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    ml_policy_reset();
    assert(apply(ALL));
    assert(apply("{\"PacketFilter\":[{\"SrcIPs\":[\"100.64.0.1-100.64.0.2\"],\"IPProto\":[6],\"DstPorts\":[{\"IP\":\"192.0.2.0/24\",\"Ports\":{\"First\":100,\"Last\":102}}]}]}"));
    assert(rx(4,6,"100.64.0.2","192.0.2.255",40000,102,2,key_b));
    assert(!rx(4,6,"100.64.0.2","192.0.2.255",40000,103,2,key_b));
    assert(apply("{\"Node\":{\"AllowedIPs\":[\"100.64.0.10/32\"]}}"));
    assert(!rx(4,6,"100.64.0.2","192.0.2.255",40000,102,2,key_b));
    assert(apply(ALL));
    assert(apply("{\"PacketFilter\":[{\"SrcIPs\":[\"fd7a:115c:a1e0::1-fd7a:115c:a1e0::2\"],\"IPProto\":[17],\"DstPorts\":[{\"IP\":\"fd7a:115c:a1e0::10/128\",\"Ports\":{\"First\":53530,\"Last\":53530}}]}]}"));
    assert(rx(6,17,"fd7a:115c:a1e0::2","fd7a:115c:a1e0::10",40000,53530,0,key_b));
    assert(!rx(6,17,"fd7a:115c:a1e0::2","fd7a:115c:a1e0::10",40000,53531,0,key_b));
    puts("PASS: all snapshot capacity/name limits fail closed; IPv4/IPv6 ranges, CIDR endpoints, port-range bounds, local AllowedIPs shrink");
}
static void *reader(void *unused) {
    (void)unused;
    for(unsigned i=0;i<15000;i++) {
        (void)rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a);
        assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,22,2,key_a));
    }
    return NULL;
}
static void concurrency(void) {
    standard();pthread_t threads[3];
    for(unsigned i=0;i<3;i++)assert(!pthread_create(&threads[i],NULL,reader,NULL));
    for(unsigned i=0;i<2000;i++) {assert(apply(FULL));assert(apply("{\"PacketFilter\":[]}"));}
    for(unsigned i=0;i<3;i++)assert(!pthread_join(threads[i],NULL));
    ml_policy_reset();
    puts("PASS: 4000 atomic policy publications with three concurrent packet readers; no denied port ever admitted");
}
static cJSON *fixture_peer(unsigned id,unsigned address) {
    cJSON *p=cJSON_CreateObject();assert(p);char key[80],ip[40];
    snprintf(key,sizeof key,"nodekey:%064x",id);
    snprintf(ip,sizeof ip,"100.64.1.%u/32",address);
    assert(cJSON_AddNumberToObject(p,"ID",id));assert(cJSON_AddStringToObject(p,"Key",key));
    cJSON *addresses=cJSON_AddArrayToObject(p,"Addresses");assert(addresses);
    assert(cJSON_AddItemToArray(addresses,cJSON_CreateString(ip)));return p;
}
static void peer_replacement(void) {
    ml_policy_reset();cJSON *full=cJSON_Parse("{" NODE ",\"PacketFilter\":[" ALL_RULE "]}");assert(full);
    cJSON *peers=cJSON_AddArrayToObject(full,"Peers");assert(peers);
    for(unsigned id=1;id<=16;id++)assert(cJSON_AddItemToArray(peers,fixture_peer(id,id)));
    assert(ml_policy_apply(full));cJSON_Delete(full);
    assert(rx(4,6,"100.64.1.1","100.64.0.10",40000,80,2,key_a));
    cJSON *delta=cJSON_Parse("{\"PeersRemoved\":[1],\"PeersChanged\":[]}");assert(delta);
    assert(cJSON_AddItemToArray(cJSON_GetObjectItemCaseSensitive(delta,"PeersChanged"),fixture_peer(17,17)));
    assert(ml_policy_apply(delta));cJSON_Delete(delta);
    uint8_t new_key[32]={[31]=17};
    assert(!rx(4,6,"100.64.1.1","100.64.0.10",40000,80,2,key_a));
    assert(rx(4,6,"100.64.1.17","100.64.0.10",40000,80,2,new_key));
    assert(rx(4,6,"100.64.1.2","100.64.0.10",40000,80,2,key_b));
    /* Official delta order: remove first, then upsert; re-added ID wins. */
    delta=cJSON_Parse("{\"PeersRemoved\":[2],\"PeersChanged\":[]}");assert(delta);
    cJSON *rotated=fixture_peer(18,2);assert(cJSON_ReplaceItemInObjectCaseSensitive(rotated,"ID",cJSON_CreateNumber(2)));
    assert(cJSON_AddItemToArray(cJSON_GetObjectItemCaseSensitive(delta,"PeersChanged"),rotated));
    assert(ml_policy_apply(delta));cJSON_Delete(delta);new_key[31]=18;
    assert(!rx(4,6,"100.64.1.2","100.64.0.10",40000,80,2,key_b));
    assert(rx(4,6,"100.64.1.2","100.64.0.10",40000,80,2,new_key));
    /* Nonempty full Peers takes precedence over all peer deltas. */
    full=cJSON_Parse("{\"Peers\":[" PEER_A "],\"PeersChanged\":[" PEER_B "],\"PeersRemoved\":[1],\"PeersChangedPatch\":[{\"NodeID\":1,\"Expired\":true}]}");assert(full);
    assert(ml_policy_apply(full));cJSON_Delete(full);
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    assert(!rx(4,6,"100.64.0.2","100.64.0.10",40000,80,2,key_b));
    assert(apply("{\"KeepAlive\":true,\"PacketFilter\":[],\"PeersRemoved\":[1]}"));
    assert(rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    ml_policy_reset();
    assert(apply("{\"KeepAlive\":true," NODE "," PEER_LIST ",\"PacketFilter\":[" ALL_RULE "]}"));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    puts("PASS: full-capacity peer replacement, removal-before-upsert, full-map precedence and keepalive fields cannot mutate/initialize authority");
}
int main(void) {
    peer_replacement();basics();deltas();replies();invalid();ownership();bounds_and_ranges();concurrency();
    printf("RESOURCE BOUNDS: snapshot=%zu bytes; two during normal update=%zu; return cache=%zu (inside PSRAM snapshot); entries=%d peers=%d groups=%d flows=%d\n",sizeof(policy),2*sizeof(policy),sizeof(((policy*)0)->flows),ENTRIES,PEERS,GROUPS,FLOWS);
}
'''

# Same translation unit exposes implementation sizes/helpers, not a reimplementation.
PROGRAM = '#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n' + HEAD + BODY
wg_source=(ML/'components/wireguard_lwip/src/wireguardif.c').read_text(encoding='utf-8')
wg_receive='static void wireguardif_process_data_message'+wg_source.split('static void wireguardif_process_data_message',1)[1].split('\nstatic struct pbuf *wireguardif_initiate_handshake',1)[0]
WG_FIXTURE = r'''
/* Execute the ACTUAL receive function. Crypto/replay and netif are explicit
 * test doubles, NOT a real encrypted transport or a physical packet trace. */
#define LWIP_IPV4 1
#define LWIP_IPV6 1
#define WIREGUARD_MAX_SRC_IPS 4
#define WIREGUARD_AUTHTAG_LEN 16
#define REJECT_AFTER_TIME 180000
#define REKEY_TIMEOUT 5
#define PBUF_TRANSPORT 0
#define PBUF_RAM 0
#define ERR_OK 0
#define IPADDR_TYPE_V4 4
#define IPADDR_TYPE_V6 6
#define IPADDR_TYPE_V4 4
typedef uint16_t u16_t;
typedef struct {uint32_t addr;uint8_t type;} ip_addr_t;
struct netif {int (*input)(struct pbuf*,struct netif*);};
struct wireguard_device {struct netif *netif;};
struct wireguard_keypair {bool receiving_valid,initiator;uint32_t keypair_millis,last_rx;};
struct wireguard_allowed_ip {bool valid;ip_addr_t ip,mask;};
struct wireguard_peer {uint8_t public_key[32];struct wireguard_allowed_ip allowed_source_ips[4];uint32_t last_rx,last_data_tx,keepalive_interval;bool send_handshake;struct wireguard_keypair kp;};
struct message_transport_data {uint32_t receiver;uint8_t counter[8],enc_packet[160];};
struct ip_hdr {uint8_t vhl,tos;uint16_t len,id,offset;uint8_t ttl,proto;uint16_t check;uint32_t src,dest;};
#define IPH_V(h) ((h)->vhl>>4)
#define IPH_LEN(h) ((h)->len)
#define PP_NTOHS(n) ntohs(n)
#define ip_addr_copy_from_ip4(a,b) do{(a).addr=(b);(a).type=4;(void)(a);}while(0)
#define IP_ADDR_NETCMP_COMPAT(s,i,m) (((s)->addr & (m)->addr)==((i)->addr & (m)->addr))
#define IP_IS_V4(a) ((a)->type==4)
#define ip_2_ip4(a) (a)
#define ip4_addr_get_u32(a) ((a)->addr)
#define lwip_ntohl(n) ntohl(n)
#define ip_addr_copy(a,b) ((a)=(b))
#define ip_addr_set_any(t,a) do{(a)->addr=0;(a)->type=(t);}while(0)
#define U8TO64_LITTLE(n) ((uint64_t)(n)[0])
#define WG_DEBUG(...) ((void)0)
static bool crypto_ok=true;
static unsigned deliveries,translations,allocs,frees;
static struct wireguard_keypair *get_peer_keypair_for_idx(struct wireguard_peer *p,uint32_t idx){(void)idx;return &p->kp;}
static bool wireguard_expired(uint32_t a,uint32_t b){(void)a;(void)b;return false;}
static uint32_t wireguard_sys_now(void){return clock_ms;}
static void update_peer_addr(struct wireguard_peer *p,const ip_addr_t *a,u16_t port,bool payload){(void)p;(void)a;(void)port;(void)payload;}
static struct wireguard_keypair *keypair_update(struct wireguard_peer *p,struct wireguard_keypair *k){(void)p;return k;}
static void keypair_destroy(struct wireguard_keypair *k){k->receiving_valid=false;}
static void netif_set_link_up(struct netif *n){(void)n;}
static struct pbuf *pbuf_alloc(int type,size_t len,int storage){
    (void)type;(void)storage;struct pbuf *p=calloc(1,sizeof *p);assert(p);p->payload=calloc(1,len?len:1);assert(p->payload);p->len=p->tot_len=len;allocs++;return p;
}
static void pbuf_free(struct pbuf *p){free(p->payload);free(p);frees++;}
static bool wireguard_decrypt_packet(void *dst,const void *src,size_t len,uint64_t nonce,struct wireguard_keypair *k){
    (void)nonce;(void)k;if(!crypto_ok)return false;assert(len>=16);memcpy(dst,src,len-16);return true;
}
static int deliver(struct pbuf *p,struct netif *n){(void)n;deliveries++;pbuf_free(p);return ERR_OK;}
static bool translate(struct pbuf *p,struct netif *n,const ip_addr_t *a){(void)n;(void)a;translations++;pbuf_free(p);return true;}
static bool (*fourvia6_translate_wg_input)(struct pbuf*,struct netif*,const ip_addr_t*)=translate;
static bool (*rx_hook)(const struct pbuf*,const uint8_t[32])=ml_policy_rx;
#define ml_policy_rx rx_hook
static struct pbuf *(*reassembly_hook)(struct pbuf*,const uint8_t[32]);
#define ml_reassemble_rx reassembly_hook
'''
WG_TESTS = r'''
#undef ml_policy_rx
int main(void) {
    struct netif n={.input=deliver};struct wireguard_device d={.netif=&n};
    (void)key_b;
    struct wireguard_peer peer={.kp={.receiving_valid=true}};memcpy(peer.public_key,key_a,32);
    peer.allowed_source_ips[0]=(struct wireguard_allowed_ip){.valid=true,.ip={.addr=htonl(0x64400001),.type=4},.mask={.addr=0xffffffff,.type=4}};
    ip_addr_t outer={0};
    for(unsigned scenario=0;scenario<8;scenario++) {
        standard();crypto_ok=true;deliveries=translations=0;
        bool ipv6=scenario>=4;
        struct pbuf p=packet(ipv6?6:4,6,ipv6?"fd7a:115c:a1e0::1":"100.64.0.1",ipv6?"fd7a:115c:a1e0:b1a:0:1:c000:232":"100.64.0.10",40000,scenario==1?22:80,2,0);
        if(scenario==2)crypto_ok=false;
        if(scenario==3)assert(apply("{\"PeersRemoved\":[1]}"));
        if(scenario>=4)assert(apply(ALL));
        if(scenario==5)memcpy((uint8_t*)p.payload+8,(uint8_t[]){0xfd,0x7a,0x11,0x5c,0xa1,0xe0,0,0,0,0,0,0,0,0,0,2},16);
        if(scenario==6)assert(apply("{\"PacketFilter\":[]}"));
        if(scenario==7)crypto_ok=false;
        struct message_transport_data hdr={0};memcpy(hdr.enc_packet,p.payload,p.tot_len);
        wireguardif_process_data_message(&d,&peer,&hdr,p.tot_len+16,&outer,1234);
        assert(deliveries==(unsigned)(scenario==0));assert(translations==(unsigned)(scenario==4));assert(allocs==frees);
    }
    /* Empty encrypted keepalive still bypasses IP policy without delivering data. */
    ml_policy_reset();crypto_ok=true;struct message_transport_data empty={0};
    wireguardif_process_data_message(&d,&peer,&empty,16,&outer,1234);assert(allocs==frees);
    puts("PASS: actual WG receive C: post-decrypt TCP allow/deny, crypto failure, stale peer revoke; IPv6 source/policy before 4via6 translation; balanced pbuf ownership (MOCK crypto/netif)");
}
'''
PBUF = r'''
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
struct pbuf {struct pbuf *next;void *payload;uint16_t tot_len,len;};
static uint16_t pbuf_copy_partial(const struct pbuf *p,void *dst,uint16_t len,uint16_t offset) {
    unsigned n=0;
    while(p && offset>=p->len){offset-=p->len;p=p->next;}
    while(p && n<len){unsigned k=p->len-offset;if(k>len-n)k=len-n;memcpy((uint8_t*)dst+n,(uint8_t*)p->payload+offset,k);n+=k;offset=0;p=p->next;}
    return n;
}
'''

with tempfile.TemporaryDirectory(prefix='tailnet-authorization-') as directory:
    path = Path(directory)
    (path / 'lwip').mkdir()
    (path / 'lwip/pbuf.h').write_text(PBUF, encoding='utf-8')
    flags = ['-std=c11', '-pthread', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
             '-I', str(path), '-I', str(ML/'include'), '-I', str(ML/'src')]
    libs = ['-lws2_32'] if os.name == 'nt' else ['-lm']
    dep = os.environ.get('CJSON_SOURCE')
    if dep:
        flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('POLICY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if os.environ.get('POLICY_NO_PIE') == '1' and os.name != 'nt':
            flags += ['-fno-pie', '-no-pie']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    for program in (PROGRAM, '#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n'+HEAD+WG_FIXTURE+wg_receive+WG_TESTS):
        (path/'test.c').write_text(program,encoding='utf-8')
        subprocess.run([os.environ.get('CC','gcc'), *flags, '-Wno-unused-function', str(path/'test.c'), '-o',str(binary), *libs], check=True)
        with (path/'run.log').open('w+b') as log:
            error = None
            try:
                subprocess.run([str(binary)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as caught:
                error = caught
            log.seek(0,2);log.seek(max(0,log.tell()-16384));print(log.read().decode(errors='replace'),end='')
            if error:
                raise error

# Wiring checks are structural evidence only, not crypto/ESP/network tests.
coord=(ML/'src/ml_coord.c').read_text(encoding='utf-8')
wg=(ML/'components/wireguard_lwip/src/wireguardif.c').read_text(encoding='utf-8')
assert 'apply_peer_map(ml,map_json)' in coord and 'apply_peer_map(ml,update_json)' in coord
apply_map=coord[coord.index('static bool apply_peer_map('):].split('\n}',1)[0]
assert apply_map.index('ml_policy_apply(map)') < apply_map.index('parse_peers_from_map_response(ml,map)')
assert 'ml_policy_reset()' in apply_map
receive=wg[wg.index('static void wireguardif_process_data_message'):]
assert receive.index('wireguard_decrypt_packet') < receive.index('ml_policy_rx(pbuf, peer->public_key)') < receive.index('translated_4via6 = fourvia6_translate_wg_input')
assert 'fragment_kind=q && ml_fragment_tx_check' in wg
assert '!fragment_kind && ml_policy_tx && !ml_policy_tx(q, peer->public_key)' in wg
assert 'ml_fragment_tx_result(q,peer->public_key,result==ERR_OK)' in wg
assert 'q && result == ERR_OK && ml_policy_sent' in wg
close=coord[coord.index('static void ml_conn_close'):].split('\n}',1)[0]
assert 'ml_policy_suspend()' in close
# Stream start keeps authority only if a complete map of this connection exists.
assert 'if (!ml_policy_authority_active()) ml_policy_suspend();' in coord[coord.index('static int do_start_long_poll'):].split('\n}',1)[0]
assert 'ml_policy_reset(); /* Explicit disconnect' in coord
print('PASS: source wiring: both map paths, RX post-decrypt/pre-translation, TX and sent-success hooks, reconnect suspension/full-map barrier (not end-to-end proof)')
