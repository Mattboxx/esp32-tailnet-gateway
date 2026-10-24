"""Execute the real pinned lwIP input/NAPT/pbuf path with synthetic interfaces.

LWIP_SOURCE points to the ESP-IDF 5.5.3 lwIP checkout (src/include exists).
Transport endpoints, route selection and timers are fixtures, not a real VPN.
Packets reach the SDK's actual IPv4 input and receive-DNAT implementation.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sdk=Path(os.environ['LWIP_SOURCE'])
assert (sdk/'src/core/ipv4/ip4_napt.c').is_file()
source=(ROOT/'main/tailnet_forward.c').read_text(encoding='utf-8')
policy='int tailnet_forward_snapshot_mappings'+source.split('int tailnet_forward_snapshot_mappings',1)[1]
core=(ROOT/'main/tailnet_input.c').read_text(encoding='utf-8')

options=r'''
#define NO_SYS 1
#define SYS_LIGHTWEIGHT_PROT 0
#define MEM_LIBC_MALLOC 1
#define MEMP_MEM_MALLOC 1
#define LWIP_NETCONN 0
#define LWIP_SOCKET 0
#define LWIP_DNS 0
#define LWIP_ARP 0
#define LWIP_ETHERNET 0
#define LWIP_IPV6 0
#define LWIP_IPV4 1
#define LWIP_TCP 1
#define TCP_QUEUE_OOSEQ 0
#define LWIP_UDP 1
#define LWIP_ICMP 0
#define LWIP_IGMP 0
#define LWIP_RAW 0
#define LWIP_DHCP 0
#define LWIP_AUTOIP 0
#define LWIP_NETIF_LOOPBACK 0
#define LWIP_STATS 0
#define ESP_LWIP 1
#define IP_FORWARD 1
#define IP_NAPT 1
#define IP_NAPT_PORTMAP 1
#define IP_REASSEMBLY 0
#define IP_FRAG 0
#define CHECKSUM_CHECK_IP 0
#define CHECKSUM_CHECK_TCP 0
#define CHECKSUM_CHECK_UDP 0
#define LWIP_HOOK_FILENAME "test_hooks.h"
#define LWIP_HOOK_IP4_ROUTE_SRC test_route
'''
arch=r'''
#include <stdio.h>
#include <stdlib.h>
#define BYTE_ORDER LITTLE_ENDIAN
#define LWIP_PLATFORM_DIAG(x) do { printf x; } while(0)
#define LWIP_PLATFORM_ASSERT(x) do { fprintf(stderr,"%s\n",x);abort(); } while(0)
#define PACK_STRUCT_STRUCT __attribute__((packed))
#define LWIP_RAND() ((unsigned)1234567)
'''
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lwip/netif.h"
#include "lwip/ip4.h"
#include "lwip/ip4_frag.h"
#include "lwip/inet_chksum.h"
#include "lwip/lwip_napt.h"
#include "lwip/priv/tcp_priv.h"
#include "lwip/udp.h"
#include "lwip/timeouts.h"
#include "lwip/tcpip.h"
#include "tailnet_reassembly.h"
typedef int esp_err_t;
#include "tailnet_forward.h"
/* Permanent-lease fixture; not a real expiry/NVS timing test. */
static bool service_lease_allowed(int i,const tailnet_forward_rule_t *r){(void)i;(void)r;return true;}
static int lock_depth;
#define LOCK() do { assert(!lock_depth);++lock_depth; } while(0)
#define UNLOCK() do { assert(lock_depth==1);--lock_depth; } while(0)
static tailnet_forward_rule_t s_rules[TAILNET_FORWARD_MAX];
static tailnet_forward_runtime_t s_runtime[TAILNET_FORWARD_MAX];
static int s_count;
static uint32_t fixture_uptime_s=1;
#define TF_UPTIME_S() fixture_uptime_s
static uint64_t s_generation=1;
typedef struct { bool installed;tailnet_forward_mapping_t mapping; } active_mapping_t;
static active_mapping_t s_active[TAILNET_FORWARD_MAX];
static size_t strlcpy(char *d,const char *s,size_t z) { size_t n=strlen(s);if(z){size_t c=n<z-1?n:z-1;memcpy(d,s,c);d[c]=0;}return n; }
struct netif *netif_list,*netif_default;
union tcp_listen_pcbs_t tcp_listen_pcbs;
struct udp_pcb *udp_pcbs;
static struct netif sta,ap,wg;
static unsigned forwarded,local_packets;
static uint8_t last_packet[256];
static uint16_t last_size;
static bool coalesce_failure;
struct pbuf *__real_pbuf_coalesce(struct pbuf *p,pbuf_layer layer);
struct pbuf *__wrap_pbuf_coalesce(struct pbuf *p,pbuf_layer layer) {
    return coalesce_failure?p:__real_pbuf_coalesce(p,layer);
}
typedef struct { sys_timeout_handler fn;void *arg; } fixture_timer_t;
static fixture_timer_t timers[16];
static uint32_t clock_ms=1000;
static bool queue_failure;
u32_t sys_now(void) { return clock_ms; }
err_t tcpip_try_callback(tcpip_callback_fn fn,void *arg) {
    if(queue_failure)return ERR_MEM;
    fn(arg);return ERR_OK;
}
void sys_timeout(u32_t ms,sys_timeout_handler fn,void *arg) {
    (void)ms;
    for(unsigned i=0;i<16;i++)assert(timers[i].fn!=fn||timers[i].arg!=arg);
    for(unsigned i=0;i<16;i++)if(!timers[i].fn){timers[i]=(fixture_timer_t){fn,arg};return;}
    assert(false);
}
void sys_untimeout(sys_timeout_handler fn,void *arg) {
    for(unsigned i=0;i<16;i++)if(timers[i].fn==fn&&timers[i].arg==arg)timers[i]=(fixture_timer_t){0};
}
static void advance_timers(void) {
    clock_ms+=1000;tailnet_reassembly_refresh();
    fixture_timer_t ready[16];memcpy(ready,timers,sizeof ready);memset(timers,0,sizeof timers);
    for(unsigned i=0;i<16;i++)if(ready[i].fn)ready[i].fn(ready[i].arg);
}
void tcp_input(struct pbuf *p,struct netif *n) { (void)n;++local_packets;pbuf_free(p); }
void udp_input(struct pbuf *p,struct netif *n) { (void)n;++local_packets;pbuf_free(p); }
struct netif *test_route(const ip4_addr_t *src,const ip4_addr_t *dst) {
    (void)src;return (lwip_ntohl(dst->addr)&0xffc00000u)==0x64400000u ? &wg : &sta;
}
static err_t output(struct netif *n,struct pbuf *p,const ip4_addr_t *dest) {
    assert(n==&wg&&lwip_ntohl(dest->addr)==0x64400002);++forwarded;
    last_size=p->tot_len;assert(last_size<=sizeof last_packet);
    assert(pbuf_copy_partial(p,last_packet,last_size,0)==last_size);return ERR_OK;
}
static struct pbuf *packet(uint8_t proto,uint32_t src,uint16_t offset,uint16_t payload) {
    struct pbuf *p=pbuf_alloc(PBUF_RAW,(u16_t)(20+payload),PBUF_RAM);assert(p);
    memset(p->payload,0,p->len);uint8_t *b=p->payload;
    b[0]=0x45;b[2]=(20+payload)>>8;b[3]=20+payload;b[4]=0x12;b[5]=0x34;
    b[6]=offset>>8;b[7]=offset;b[8]=64;b[9]=proto;
    uint32_t address=lwip_htonl(src);memcpy(b+12,&address,4);
    address=netif_ip4_addr(&sta)->addr;memcpy(b+16,&address,4);
    b[20]=0x30;b[21]=0x39;b[22]=0x08;b[23]=0xae; /* listener 2222 */
    if(proto==6&&payload>=20)b[32]=0x50;
    if(proto==17&&payload>=8) { b[24]=payload>>8;b[25]=payload; }
    uint16_t sum=inet_chksum(b,20);memcpy(b+10,&sum,2);return p;
}
static struct pbuf *piece(uint8_t proto,uint16_t id,uint16_t offset,uint16_t length,uint8_t fill) {
    struct pbuf *p=packet(proto,0xc0000263,offset,length);uint8_t *h=p->payload;
    h[4]=id>>8;h[5]=id;h[10]=h[11]=0;
    uint16_t sum=inet_chksum(h,20);memcpy(h+10,&sum,2);
    memset(h+20,fill,length);return p;
}
static void assembled(struct pbuf *p,uint8_t first,uint8_t last) {
    assert(p&&p->tot_len==52);uint8_t bytes[52];
    assert(pbuf_copy_partial(p,bytes,sizeof bytes,0)==sizeof bytes);
    assert(!bytes[6]&&!bytes[7]&&inet_chksum(bytes,20)==0);
    for(unsigned i=20;i<28;i++)assert(bytes[i]==first);
    for(unsigned i=28;i<52;i++)assert(bytes[i]==last);
    pbuf_free(p);
}
static void isolated_reassembly(const char *scenario,uint8_t proto) {
    if(!strcmp(scenario,"interface-isolation")) {
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        assert(!tailnet_reassemble(piece(proto,77,1,24,4),&ap));
        assembled(tailnet_reassemble(piece(proto,77,1,24,2),&sta),1,2);
        assembled(tailnet_reassemble(piece(proto,77,0x2000,8,3),&ap),3,4);
    } else if(!strcmp(scenario,"protocol-isolation")) {
        uint8_t other=proto==6?17:6;
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        assert(!tailnet_reassemble(piece(other,77,1,24,4),&sta));
        assembled(tailnet_reassemble(piece(proto,77,1,24,2),&sta),1,2);
        assembled(tailnet_reassemble(piece(other,77,0x2000,8,3),&sta),3,4);
    } else if(!strcmp(scenario,"native-isolation")) {
        struct netif *previous=ip_data.current_input_netif;ip_data.current_input_netif=&ap;
        assert(!ip4_reass(piece(proto,77,1,24,4)));ip_data.current_input_netif=previous;
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        assembled(tailnet_reassemble(piece(proto,77,1,24,2),&sta),1,2);
    } else if(!strcmp(scenario,"overlap")) {
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,9),&sta));
        assert(!tailnet_reassemble(piece(proto,77,0x2000,16,9),&sta));
        assembled(tailnet_reassemble(piece(proto,77,1,24,2),&sta),1,2);
    } else if(!strcmp(scenario,"expiry")) {
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        for(unsigned i=0;i<IP_REASS_MAXAGE+3;i++)advance_timers();
        assert(!tailnet_reassemble(piece(proto,77,1,24,2),&sta));
        assembled(tailnet_reassemble(piece(proto,77,0x2000,8,3),&sta),3,2);
    } else if(!strcmp(scenario,"expiry-queue-failure")||!strcmp(scenario,"expiry-wrap")) {
        if(!strcmp(scenario,"expiry-wrap"))clock_ms=UINT32_MAX-4000;
        assert(!tailnet_reassemble(piece(proto,77,0x2000,8,1),&sta));
        queue_failure=true;
        for(unsigned i=0;i<IP_REASS_MAXAGE+3;i++)advance_timers();
        /* Packet-time expiry still works even if every idle callback fails. */
        assert(!tailnet_reassemble(piece(proto,77,1,24,2),&sta));
        assembled(tailnet_reassemble(piece(proto,77,0x2000,8,3),&sta),3,2);
    } else if(!strcmp(scenario,"chain-capacity")) {
        struct pbuf *first=piece(proto,77,0x2000,8,1);
        for(unsigned i=1;i<IP_REASS_MAX_PBUFS;i++) {
            struct pbuf *part=pbuf_alloc(PBUF_RAW,8,PBUF_RAM);assert(part);
            memset(part->payload,1,8);pbuf_cat(first,part);
        }
        uint8_t *h=first->payload;h[2]=first->tot_len>>8;h[3]=first->tot_len;
        h[10]=h[11]=0;uint16_t sum=inet_chksum(h,20);memcpy(h+10,&sum,2);
        assert(!tailnet_reassemble(first,&sta));
        assert(!tailnet_reassemble(piece(proto,77,IP_REASS_MAX_PBUFS,24,2),&sta));
        for(unsigned i=0;i<IP_REASS_MAXAGE+3;i++)advance_timers();
        assert(!tailnet_reassemble(piece(proto,77,1,24,2),&sta));
        assembled(tailnet_reassemble(piece(proto,77,0x2000,8,3),&sta),3,2);
    } else if(!strcmp(scenario,"mutations")) {
        uint32_t seed=1234567;
        for(unsigned i=0;i<20000;i++) {
            seed=seed*1664525u+1013904223u;
            unsigned length=4+(seed&127),offset=(seed>>16)&0x3fff;
            struct pbuf *p=piece(proto,(seed>>8)&31,offset,length,seed);
            uint8_t *h=p->payload;
            if(seed&1)h[(seed>>2)%20]^=seed>>24;
            if(seed&2){h[10]=h[11]=0;uint16_t sum=inet_chksum(h,20);memcpy(h+10,&sum,2);}
            struct pbuf *result=tailnet_reassemble(p,(seed&4)?&sta:&ap);
            if(result) {
                assert(result->tot_len>=20&&result->tot_len<=65535);
                assert(inet_chksum(result->payload,20)==0);pbuf_free(result);
            }
            if(i%97==0)advance_timers();
        }
    } else if(!strcmp(scenario,"capacity")) {
        /* Distinct first fragments exceed the bounded context count. */
        for(unsigned i=0;i<IP_REASS_MAX_PBUFS+2;i++)
            assert(!tailnet_reassemble(piece(proto,100+i,0x2000,8,1),&sta));
        assert(!tailnet_reassemble(piece(proto,100,1,24,2),&sta));
        assembled(tailnet_reassemble(piece(proto,100,0x2000,8,3),&sta),3,2);
    } else assert(false);
}
'''
tests=r'''
int main(int argc,char **argv) {
    assert(argc==3);bool fragment=strcmp(argv[1],"plain")!=0;uint8_t proto=atoi(argv[2]);assert(proto==6||proto==17);
    sta.name[0]='s';sta.name[1]='t';ap.name[0]='a';ap.name[1]='p';wg.name[0]='w';wg.name[1]='g';
    sta.flags=ap.flags=wg.flags=NETIF_FLAG_UP|NETIF_FLAG_LINK_UP;
    ip4_addr_t addr={lwip_htonl(0xc0000201)},mask={lwip_htonl(0xffffff00)};
    ip_addr_copy_from_ip4(sta.ip_addr,addr);ip_addr_copy_from_ip4(sta.netmask,mask);
    addr.addr=lwip_htonl(0xc0000301);ip_addr_copy_from_ip4(ap.ip_addr,addr);ip_addr_copy_from_ip4(ap.netmask,mask);
    addr.addr=lwip_htonl(0x64400001);ip_addr_copy_from_ip4(wg.ip_addr,addr);ip_addr_copy_from_ip4(wg.netmask,mask);
    sta.next=&ap;ap.next=&wg;netif_list=netif_default=&sta;wg.output=output;
    assert(ip_napt_enable_netif(&ap,1));
    s_count=1;s_rules[0]=(tailnet_forward_rule_t){.valid=1,.enabled=1,.proto=proto,.listen_port=2222,.destination_port=22,.source_network=0xc0000200,.source_prefix=24};
    s_runtime[0].resolved_ip=0x64400002;
    tailnet_forward_mapping_t mapping;assert(tailnet_forward_snapshot_mappings(&mapping,1)==1);
    mapping.binding_ip_nbo=netif_ip4_addr(&sta)->addr;tailnet_forward_mark_installed(&mapping,true,NULL);
    assert(ip_portmap_add(proto,mapping.binding_ip_nbo,2222,mapping.destination_nbo,22));
    if(strstr(argv[1],"isolation")||!strcmp(argv[1],"overlap")||strstr(argv[1],"expiry")||strstr(argv[1],"capacity")||!strcmp(argv[1],"mutations")) {
        isolated_reassembly(argv[1],proto);assert(!forwarded&&!local_packets);
    } else if(!strcmp(argv[1],"plain")||!strcmp(argv[1],"fragment")) {
        struct pbuf *p=packet(proto,0xc6336402,fragment?1:0,32);
        assert(__wrap_ip4_input(p,&sta)==ERR_OK);
        assert(!forwarded&&!local_packets); /* unauthorized source must never reach WG output */
    } else if(!strcmp(argv[1],"split")||!strcmp(argv[1],"split-oom")) {
        struct pbuf *whole=packet(proto,0xc0000263,0,32);
        struct pbuf *first=pbuf_alloc(PBUF_RAW,22,PBUF_RAM),*rest=pbuf_alloc(PBUF_RAW,30,PBUF_RAM);
        assert(first&&rest);memcpy(first->payload,whole->payload,22);memcpy(rest->payload,(uint8_t*)whole->payload+22,30);
        pbuf_cat(first,rest);pbuf_free(whole);coalesce_failure=!strcmp(argv[1],"split-oom");
        assert(__wrap_ip4_input(first,&sta)==ERR_OK);
        assert(forwarded==(unsigned)!coalesce_failure&&!local_packets);
    } else if(!strcmp(argv[1],"short")) {
        struct pbuf *p=packet(proto,0xc0000263,0,4);
        assert(__wrap_ip4_input(p,&sta)==ERR_OK && !forwarded && !local_packets);
    } else if(!strcmp(argv[1],"complete")||!strcmp(argv[1],"denied")||!strcmp(argv[1],"oom")||!strcmp(argv[1],"bad-checksum")) {
        uint32_t src=!strcmp(argv[1],"denied")?0xc6336402:0xc0000263;
        uint8_t transport[32]={0};transport[0]=0x30;transport[1]=0x39;transport[2]=0x08;transport[3]=0xae;
        if(proto==6)transport[12]=0x50;else transport[5]=sizeof transport;
        struct pbuf *first=packet(proto,src,0x2000,8),*last=packet(proto,src,1,24);
        memcpy((uint8_t*)first->payload+20,transport,8);memcpy((uint8_t*)last->payload+20,transport+8,24);
        bool bad_checksum=!strcmp(argv[1],"bad-checksum");
        if(bad_checksum)((uint8_t*)first->payload)[10]^=1;
        coalesce_failure=!strcmp(argv[1],"oom");
        /* Last-fragment-first ordering and a small first TCP fragment. */
        assert(__wrap_ip4_input(last,&sta)==ERR_OK && !forwarded);
        assert(__wrap_ip4_input(first,&sta)==ERR_OK);
        unsigned expected=!strcmp(argv[1],"complete")||(!strcmp(argv[1],"oom")&&proto==17);
        assert(forwarded==expected&&!local_packets);
        if(expected) {
            assert(last_size==52&&last_packet[6]==0&&last_packet[7]==0);
            assert(last_packet[22]==0&&last_packet[23]==22);
            uint32_t dest;memcpy(&dest,last_packet+16,4);assert(dest==mapping.destination_nbo);
            assert(inet_chksum(last_packet,20)==0);
            unsigned header_size=proto==6?20:8;
            assert(!memcmp(last_packet+20+header_size,transport+header_size,sizeof transport-header_size));
        }
    } else assert(false);
    /* Expire both isolated and native incomplete datagrams, then release pools. */
#if IP_REASSEMBLY
    for(unsigned i=0;i<IP_REASS_MAXAGE+3;i++){ip_reass_tmr();advance_timers();}
#endif
    assert(ip_napt_enable_netif(&ap,0));
    printf("PASS: actual SDK IPv4/NAPT/pbuf - %s protocol %u\n",argv[1],proto);
}
'''

with tempfile.TemporaryDirectory(prefix='tailnet-sdk-') as directory:
    path=Path(directory);(path/'arch').mkdir();(path/'lwip').mkdir()
    # NO_SYS deliberately omits the production TCP/IP thread. Supply only
    # its callback declaration; fixture execution/failure is deterministic.
    (path/'lwip/tcpip.h').write_text('#pragma once\n#include "lwip/err.h"\ntypedef void (*tcpip_callback_fn)(void *);\nerr_t tcpip_try_callback(tcpip_callback_fn,void *);\n',encoding='utf-8')
    reassembly='CONFIG_LWIP_IP4_REASSEMBLY=y' in (ROOT/'sdkconfig.defaults').read_text(encoding='utf-8')
    (path/'lwipopts.h').write_text(options.replace('#define IP_REASSEMBLY 0',f'#define IP_REASSEMBLY {int(reassembly)}'),encoding='utf-8')
    (path/'arch/cc.h').write_text(arch,encoding='utf-8')
    (path/'test_hooks.h').write_text('struct netif *test_route(const ip4_addr_t *,const ip4_addr_t *);\n#define LWIP_HOOK_IP4_ROUTE_SRC test_route\n',encoding='utf-8')
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n',encoding='utf-8')
    # No cellular PPP netif in this SDK fixture: every interface is allowed.
    ppp='bool netif_hooks_ppp_input_allowed(struct pbuf *p,struct netif *n){(void)p;(void)n;return true;}\n'
    (path/'test.c').write_text(fixture+policy+ppp+core+tests,encoding='utf-8')
    files=['core/ip.c','core/pbuf.c','core/mem.c','core/memp.c','core/inet_chksum.c','core/def.c','core/ipv4/ip4.c','core/ipv4/ip4_addr.c','core/ipv4/ip4_napt.c','core/ipv4/ip4_frag.c']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-I',str(path),'-I',str(sdk/'src/include'),'-I',str(ROOT/'main'),'-Wl,--wrap=ip4_input','-Wl,--wrap=pbuf_coalesce']
    if os.environ.get('TAILNET_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    implementation=[str(ROOT/'main/tailnet_reassembly.c')]
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),*implementation,*(str(sdk/'src'/f) for f in files),'-o',str(binary)],check=True)
    for scenario in ('plain','fragment','short','split','split-oom','complete','denied','oom','bad-checksum',
                     'interface-isolation','protocol-isolation','native-isolation','overlap','expiry','capacity',
                     'expiry-queue-failure','expiry-wrap','chain-capacity','mutations'):
        for proto in (6,17):
            subprocess.run([str(binary),scenario,str(proto)],check=True,timeout=15)
    if os.environ.get('TAILNET_SANITIZE')=='1':
        # Confirm the old implementation really read outside short NAT headers;
        # an ordinary failing assertion is not evidence of a memory violation.
        baseline=subprocess.check_output(['git','show','eef422def7ee040fc6623ef001a143214f069887:main/tailnet_input.c'],cwd=ROOT,text=True)
        (path/'baseline.c').write_text(fixture+policy+baseline+tests,encoding='utf-8')
        before=path/'before'
        subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'baseline.c'),*implementation,*(str(sdk/'src'/f) for f in files),'-o',str(before)],check=True)
        for proto in (6,17):
            result=subprocess.run([str(before),'short',str(proto)],capture_output=True,text=True,timeout=15)
            assert result.returncode!=0 and 'heap-buffer-overflow' in result.stderr, 'Old short NAT header must reproduce an actual ASan memory violation'
        print('PASS: baseline real SDK TCP/UDP short-header heap-buffer-overflow reproduced with ASan; fixed paths pass')
