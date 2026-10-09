"""Compile the actual routing hook/diagnostic functions with synthetic netifs.

No board changes or private network data. ROUTE_SANITIZE=1 enables ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/lwip_route_hook.c').read_text(encoding='utf-8')
helpers = source.split('/* Tailscale CGNAT: 100.64.0.0/10 */', 1)[1].split('static struct netif *s_original_default', 1)[0]
hook = 'struct netif *__wrap_ip4_route_src_hook' + source.split('struct netif *__wrap_ip4_route_src_hook', 1)[1].split('/* ---------------------------------------------------------------------', 1)[0]
diagnostic = 'static void name_netif' + source.split('static void name_netif', 1)[1].split('/* ---------------------------------------------------------------------', 1)[0]
default_update = 'static void set_default_callback' + source.split('static void set_default_callback', 1)[1].split('typedef struct {', 1)[0]
napt = 'err_t __wrap_ip_napt_forward' + source.split('err_t __wrap_ip_napt_forward', 1)[1]
fixture = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
typedef struct { uint32_t addr; } ip4_addr_t;
typedef ip4_addr_t ip_addr_t;
typedef unsigned char u8_t;
#define DNS_MAX_SERVERS 2
#define IP_IS_V4(a) true
#define ip_2_ip4(a) (a)
#define ip_addr_isany(a) ((a)->addr == 0)
#define ip_addr_isany_val(a) ((a).addr == 0)
#define ip4_addr_netcmp(a,b,m) (((a)->addr & (m)->addr) == ((b)->addr & (m)->addr))
static ip_addr_t dns_servers[DNS_MAX_SERVERS];
static const ip_addr_t *dns_getserver(u8_t i) { return &dns_servers[i]; }
static struct dhcp { ip_addr_t server_ip_addr; } dhcp_state;
#define netif_dhcp_data(n) (&dhcp_state)
static uint32_t known_peer_nbo;
struct netif;
static bool microlink_wg_has_peer_ip(struct netif *wg, uint32_t ip);
struct netif { struct netif *next; char name[2]; uint8_t num, napt; bool up, link; ip4_addr_t ip, mask; };
static struct netif *netif_list, *netif_default;
#define netif_ip4_addr(n) (&(n)->ip)
#define netif_ip4_netmask(n) (&(n)->mask)
#define ip4_addr_get_u32(a) ((a)->addr)
#define ip4_addr_isany_val(a) ((a).addr == 0)
#define ip4_addr_cmp(a,b) ((a)->addr == (b)->addr)
#define netif_is_up(n) ((n)->up)
#define netif_is_link_up(n) ((n)->link)
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define lwip_htonl swap32
#define lwip_ntohs(x) ((uint16_t)(((x)>>8)|((x)<<8)))
#define ESP_LOGW(...) ((void)0)
#define ESP_OK 0
#define ERR_OK 0
static bool queue_fails;
static int tcpip_callback_wait(void (*callback)(void *), void *arg) {
    if(queue_fails) return -1;
    callback(arg); return ERR_OK;
}
static void netif_set_default(struct netif *n) { netif_default=n; }
#define TAILSCALE_ACCEPTED_ROUTES_MAX 32
typedef struct { uint32_t network; uint8_t prefix_len; } tailscale_accepted_route_t;
static tailscale_accepted_route_t tailscale_accepted_routes[TAILSCALE_ACCEPTED_ROUTES_MAX];
static int tailscale_accepted_routes_count;
static uint32_t tailscale_exit_node_ip;
static int32_t tailscale_lan_bypass, tailscale_accept_routes;
static _Thread_local int core_depth;
static atomic_int lock_count;
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(mux) do { assert(core_depth==0); assert(pthread_mutex_lock(mux)==0); core_depth=1; atomic_fetch_add(&lock_count,1); } while(0)
#define portEXIT_CRITICAL(mux) do { assert(core_depth==1); core_depth=0; assert(pthread_mutex_unlock(mux)==0); } while(0)
static bool should_log_route_hook(void) { assert(core_depth==0); return false; }
static struct netif *__real_ip4_route_src_hook(const ip4_addr_t *src, const ip4_addr_t *dst) { (void)src; (void)dst; return NULL; }
typedef struct microlink_s { int unused; } microlink_t;
static bool microlink_wg_has_peer_ip(struct netif *wg, uint32_t ip) { return wg && known_peer_nbo && ip == known_peer_nbo; }
typedef struct { char hostname[64]; uint32_t vpn_ip; int subnet_route_count; tailscale_accepted_route_t subnet_routes[32]; } microlink_peer_info_t;
static microlink_t *tailscale_get_microlink(void) { return NULL; }
static int microlink_get_peer_count(microlink_t *ml) { (void)ml; return 0; }
static int microlink_get_peer_info(microlink_t *ml, int i, microlink_peer_info_t *pi) { (void)ml; (void)i; (void)pi; return -1; }
typedef int err_t;
struct pbuf { uint16_t len; void *payload; };
struct ip_hdr { ip4_addr_t src, dest; uint8_t proto; };
#define IPH_PROTO(h) ((h)->proto)
#define IPH_HL(h) 5
static bool exit_server_active;
static int32_t tailscale_snat_subnet_routes;
static bool tailscale_exit_server_active(void) { return exit_server_active; }
static bool tailnet_forward_is_routed_target(int proto, uint32_t ip, uint16_t port) { (void)proto; (void)ip; (void)port; return false; }
static bool tailnet_forward_is_routed_response(int proto, uint32_t ip, uint16_t port) { (void)proto; (void)ip; (void)port; return false; }
static int napt_calls;
static bool napt_enabled_at_call;
static err_t __real_ip_napt_forward(struct pbuf *p, struct ip_hdr *h, struct netif *inp, struct netif *outp) {
    (void)p; (void)h; (void)outp;
    napt_calls++; napt_enabled_at_call=inp && inp->napt;
    return ERR_OK;
}
'''
tests = r'''
static struct netif sta, ap, wg;
static void reset(void) {
    sta=(struct netif){.name={'s','t'},.num=1,.up=true,.link=true,.ip={swap32(0xc0a80114)},.mask={swap32(0xffffff00)}};
    ap=(struct netif){.name={'a','p'},.num=2,.up=true,.link=true,.ip={swap32(0xc0a80401)},.mask={swap32(0xffffff00)}};
    wg=(struct netif){.name={'w','g'},.up=true,.link=true,.ip={swap32(0x6450463c)},.mask={swap32(0xffc00000)}};
    sta.next=&ap; ap.next=&wg; netif_list=&sta; netif_default=NULL;
    tailscale_exit_node_ip=0; tailscale_lan_bypass=0; tailscale_accept_routes=0;
    publish_accepted_routes(NULL,0);
    memset(dns_servers,0,sizeof dns_servers); memset(&dhcp_state,0,sizeof dhcp_state); known_peer_nbo=0;
}
static void expect(uint32_t src, uint32_t dst, struct netif *want) {
    ip4_addr_t s={swap32(src)}, d={swap32(dst)};
    assert(__wrap_ip4_route_src_hook(&s,&d)==want);
    char label[16], reason[160], expected[16];
    route_explain(src,dst,label,sizeof label,reason,sizeof reason);
    name_netif(want,expected,sizeof expected);
    if(strcmp(label,expected)) { fprintf(stderr,"route mismatch %08x -> %08x: %s != %s\n",src,dst,label,expected); abort(); }
    assert(reason[0]); assert(core_depth==0);
}
static atomic_bool producer_done;
static void *route_producer(void *arg) {
    (void)arg;
    tailscale_accepted_route_t rows[32];
    for(int gen=0;gen<20000;gen++) {
        for(int i=0;i<32;i++) rows[i]=(tailscale_accepted_route_t){0x0a000000u+(uint32_t)gen*64u+(uint32_t)i,32};
        publish_accepted_routes(rows,32);
    }
    atomic_store(&producer_done,true); return NULL;
}
int main(void) {
    reset();
    /* CGNAT local egress needs NAT too; only actual WG TCP skips it. */
    struct ip_hdr header={.dest={swap32(0x6450463d)},.proto=6};
    napt_calls=0; exit_server_active=true;
    assert(__wrap_ip_napt_forward(NULL,&header,&wg,&sta)==ERR_OK);
    assert(napt_calls==1 && napt_enabled_at_call && wg.napt==0);
    exit_server_active=false; tailscale_snat_subnet_routes=1;
    __wrap_ip_napt_forward(NULL,&header,&wg,&sta);
    assert(napt_calls==2 && napt_enabled_at_call && wg.napt==0);
    tailscale_snat_subnet_routes=0;
    __wrap_ip_napt_forward(NULL,&header,&wg,&sta);
    assert(napt_calls==3 && !napt_enabled_at_call);
    __wrap_ip_napt_forward(NULL,&header,&ap,&wg); assert(napt_calls==3);
    ap.napt=1; __wrap_ip_napt_forward(NULL,&header,&ap,&sta);
    assert(napt_calls==4 && napt_enabled_at_call && ap.napt==1);
    header.proto=17; __wrap_ip_napt_forward(NULL,&header,&ap,&wg);
    assert(napt_calls==5 && napt_enabled_at_call);
    reset();
    set_default_via_tcpip(&sta); assert(netif_default==&sta);
    queue_fails=true; set_default_via_tcpip(&wg); assert(netif_default==&sta);
    queue_fails=false; reset();
    /* New 0.1.30 CGNAT exceptions work without exit-node/LAN-bypass mode. */
    sta.ip.addr=swap32(0x64600114); sta.mask.addr=swap32(0xffc00000);
    expect(0,0x6450463d,&sta);
    known_peer_nbo=swap32(0x6450463d); expect(0,0x6450463d,&wg);
    known_peer_nbo=0; sta.mask.addr=swap32(0xffffff00);
    dns_servers[0].addr=swap32(0x64710202); expect(0,0x64710202,&sta);
    known_peer_nbo=dns_servers[0].addr; expect(0,0x64710202,&wg);
    known_peer_nbo=0; dhcp_state.server_ip_addr.addr=swap32(0x64720202);
    expect(0,0x64720202,&sta);
    sta.link=false; expect(0,0x64720202,&wg); expect(0,0x64710202,&wg);
    reset(); ap.ip.addr=swap32(0x64400401); expect(0,0x64400402,&ap);
    known_peer_nbo=swap32(0x64400402); expect(0,0x64400402,&wg);
    reset();
    sta.ip.addr=swap32(0x64600114); /* CGNAT uplink before wg in list */
    assert(find_wg_netif()==&wg);
    wg.ip.addr=0; assert(find_wg_netif()==NULL); /* boot/reconnect: never STA */
    expect(0xc0a80402,0x6450463d,NULL);
    wg.ip.addr=swap32(0x0a010101); assert(find_wg_netif()==&wg); /* identity is name */
    expect(0xc0a80402,0x6450463d,&wg);
    reset(); tailscale_exit_node_ip=0x6450463d; tailscale_lan_bypass=1;
    expect(0xc0a80402,0xc0a80164,&sta);
    expect(0x6450463d,0xc0a80402,&ap);
    expect(0xc0a80402,0x0a0a0101,&sta);
    expect(0,0xcb007107,&sta); /* local public control-plane socket */
    expect(0xc0a80402,0xcb007107,&wg); /* forwarded public exit traffic */
    assert(__wrap_ip4_route_src_hook(NULL,&(ip4_addr_t){swap32(0xcb007107)})==&sta);
    ap.link=false; expect(0x6450463d,0xc0a80402,&sta);
    ap.link=true; ap.up=false; expect(0x6450463d,0xc0a80402,&sta);
    ap.up=true; sta.link=false; expect(0xc0a80402,0xc0a80164,NULL);
    sta.link=true; sta.up=false; expect(0xc0a80402,0xc0a80164,NULL);
    sta.up=true; sta.ip.addr=swap32(0x64600114); sta.mask.addr=swap32(0xff000000);
    expect(0xc0a80402,0x64800164,&sta); /* CGNAT uplink is valid LAN bypass */
    for(int up=0;up<2;up++) for(int link=0;link<2;link++) {
        sta.up=up; sta.link=link;
        expect(0xc0a80402,0x64800164,up&&link?&sta:&wg);
    }
    reset(); tailscale_accept_routes=1;
    tailscale_accepted_route_t routes[32], snapshot[32];
    for(int i=0;i<32;i++) routes[i]=(tailscale_accepted_route_t){0x0a000000u+(i<<16),16};
    publish_accepted_routes(routes,32);
    int before=lock_count;
    assert(tailscale_accepted_routes_snapshot(snapshot,32)==32);
    assert(lock_count==before+1 && !memcmp(routes,snapshot,sizeof routes));
    assert(tailscale_accepted_routes_snapshot(snapshot,1)==1);
    assert(tailscale_accepted_routes_snapshot(NULL,32)==0);
    assert(tailscale_accepted_routes_snapshot(snapshot,0)==0);
    publish_accepted_routes(NULL,33); assert(tailscale_accepted_routes_count==32);
    publish_accepted_routes(NULL,1); assert(tailscale_accepted_routes_count==32);
    for(int i=0;i<32;i++) expect(0xc0a80402,0x0a000001u+(i<<16),&wg);
    expect(0xc0a80114,0x0a000001,NULL); /* own IP does not accept peer routes */
    expect(0,0x0a000001,NULL);
    routes[0]=(tailscale_accepted_route_t){0x0a000001,32}; publish_accepted_routes(routes,1);
    expect(0xc0a80402,0x0a000001,&wg); expect(0xc0a80402,0x0a000002,NULL);
    for(int prefix=0;prefix<=255;prefix++) {
        routes[0]=(tailscale_accepted_route_t){0x0a000001,(uint8_t)prefix}; publish_accepted_routes(routes,1);
        expect(0xc0a80402,0x0a000001,prefix>=1&&prefix<=32?&wg:NULL);
    }
    publish_accepted_routes(NULL,0); expect(0xc0a80402,0x0a000001,NULL);
    assert(ip_is_rfc1918(0x0a000000) && ip_is_rfc1918(0xac100000) && ip_is_rfc1918(0xac1fffff) && ip_is_rfc1918(0xc0a8ffff));
    assert(!ip_is_rfc1918(0xac200000) && !ip_is_rfc1918(0x64400000) && !ip_is_rfc1918(0xc0a90000));
    assert(__wrap_ip4_route_src_hook(NULL,NULL)==NULL);
    for(int i=0;i<32;i++) routes[i]=(tailscale_accepted_route_t){0x0a000000u+(uint32_t)i,32};
    publish_accepted_routes(routes,32);
    pthread_t producer; assert(!pthread_create(&producer,NULL,route_producer,NULL));
    int reads=0;
    while(!atomic_load(&producer_done) || reads<5000) {
        assert(tailscale_accepted_routes_snapshot(snapshot,32)==32);
        uint32_t base=snapshot[0].network; assert((base&63)==0);
        for(int i=0;i<32;i++) assert(snapshot[i].network==base+(uint32_t)i && snapshot[i].prefix_len==32);
        tailscale_accepted_route_t matched;
        if(accepted_route_lookup(0x0a000007,&matched)) assert(matched.network==0x0a000007 && matched.prefix_len==32);
        reads++;
    }
    assert(!pthread_join(producer,NULL));
    puts("PASS: real hook/diagnostic parity, CGNAT identity, missing WG, down/link-down interfaces, exit self/forward split, snapshots, every prefix width, queued default updates/failure and 20000 concurrent table publications");
}
'''
with tempfile.TemporaryDirectory(prefix='route-hook-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + helpers + default_update + hook + diagnostic + napt + tests, encoding='utf-8')
    flags = ['-std=c11', '-pthread', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable']
    if os.environ.get('ROUTE_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
