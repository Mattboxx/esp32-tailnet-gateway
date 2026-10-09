"""Compile actual PeerAPI authorization/decoder/resolver guards with fixtures.

No board or network access. PEER_DNS_SANITIZE=1 enables ASan/UBSan in CI.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/peer_dns.c').read_text()
functions = source.split('static bool advertises_exit_node', 1)[1].split('/* Use an explicit DNS-relay', 1)[0]
functions = 'static bool advertises_exit_node' + functions
fixture = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#define PEER_DNS_MAX_MESSAGE 4096U
#define PEER_DNS_MAX_B64 (((PEER_DNS_MAX_MESSAGE+2U)/3U)*4U)
#define AF_INET 2
#define AF_INET6 10
#define ESP_OK 0
typedef unsigned socklen_t;
typedef struct { int unused; } httpd_req_t;
typedef struct { int unused; } microlink_t;
typedef struct { uint32_t vpn_ip; } microlink_peer_info_t;
struct sockaddr_storage { uint16_t ss_family; uint8_t data[126]; };
struct sockaddr { uint16_t family; };
struct sockaddr_in { uint16_t sin_family,sin_port; struct { uint32_t s_addr; } sin_addr; };
struct sockaddr_in6 { uint16_t sin6_family,sin6_port; uint32_t flow; struct { uint8_t s6_addr[16]; } sin6_addr; };
static uint8_t mapped_prefix[12]={0,0,0,0,0,0,0,0,0,0,255,255};
#define IN6_IS_ADDR_V4MAPPED(a) (!memcmp((a)->s6_addr,mapped_prefix,12))
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define ntohl swap32
static bool active=true,connected=true,have_instance=true,socket_error;
static uint32_t own_ip=0x64500001, peer_ip=0x64500002;
static struct sockaddr_storage local_address,remote_address;
static bool tailscale_exit_server_active(void) { return active; }
static microlink_t ml;
static microlink_t *tailscale_get_microlink(void) { return have_instance?&ml:NULL; }
static bool microlink_is_connected(microlink_t *m) { (void)m; return connected; }
static uint32_t microlink_get_vpn_ip(microlink_t *m) { (void)m; return own_ip; }
static int httpd_req_to_sockfd(httpd_req_t *r) { (void)r; return socket_error?-1:4; }
static int getsockname(int f,struct sockaddr *a,socklen_t *n) { (void)f; assert(*n>=sizeof local_address); memcpy(a,&local_address,sizeof local_address); return 0; }
static int getpeername(int f,struct sockaddr *a,socklen_t *n) { (void)f; assert(*n>=sizeof remote_address); memcpy(a,&remote_address,sizeof remote_address); return 0; }
static int microlink_get_peer_count(microlink_t *m) { (void)m; return 1; }
static int microlink_get_peer_info(microlink_t *m,int i,microlink_peer_info_t *p) { (void)m; (void)i; p->vpn_ip=peer_ip; return ESP_OK; }
typedef struct { uint32_t ip; } esp_netif_t;
typedef struct { struct { uint32_t addr; } ip; } esp_netif_ip_info_t;
static esp_netif_t sta={0xc0000201},ap={0xc0000202};
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) { return !strcmp(key,"WIFI_STA_DEF")?&sta:&ap; }
static int esp_netif_get_ip_info(esp_netif_t *n,esp_netif_ip_info_t *i) { i->ip.addr=swap32(n->ip); return ESP_OK; }
static void address(struct sockaddr_storage *s,int family,uint32_t host) {
    memset(s,0,sizeof *s);
    if(family==AF_INET) { struct sockaddr_in a={.sin_family=AF_INET,.sin_addr={swap32(host)}}; memcpy(s,&a,sizeof a); }
    else { struct sockaddr_in6 a={.sin6_family=AF_INET6}; memcpy(a.sin6_addr.s6_addr,mapped_prefix,12); uint32_t n=swap32(host); memcpy(a.sin6_addr.s6_addr+12,&n,4); memcpy(s,&a,sizeof a); }
}
'''
tests = r'''
int main(void) {
    httpd_req_t req={0};
    for(int i=0;i<2;i++) {
        int family=i?AF_INET6:AF_INET;
        address(&local_address,family,own_ip); address(&remote_address,family,peer_ip);
        assert(peer_request_allowed(&req));
        address(&local_address,family,sta.ip); assert(!peer_request_allowed(&req));
        address(&local_address,family,own_ip);
        address(&remote_address,family,0x64500003); assert(!peer_request_allowed(&req));
        address(&remote_address,family,peer_ip);
        active=false; assert(!peer_request_allowed(&req)); active=true;
        connected=false; assert(!peer_request_allowed(&req)); connected=true;
        have_instance=false; assert(!peer_request_allowed(&req)); have_instance=true;
        socket_error=true; assert(!peer_request_allowed(&req)); socket_error=false;
    }
    ((struct sockaddr_in6*)&remote_address)->sin6_addr.s6_addr[0]=0x20;
    assert(!peer_request_allowed(&req));
    uint8_t decoded[4098]; size_t n=0;
    assert(decode_base64url("AA",2,decoded,4096,&n) && n==1 && decoded[0]==0);
    assert(decode_base64url("_-4",3,decoded,4096,&n) && n==2 && decoded[0]==255 && decoded[1]==238);
    for(const char **p=(const char*[]){"A","AB","AAA=","AA/","AA+","AA%","",NULL};*p;p++)
        assert(!decode_base64url(*p,strlen(*p),decoded,4096,&n));
    assert(!decode_base64url("AAAA",4,decoded,2,&n));
    uint8_t query[12]={0}; assert(dns_query_valid(query,12));
    assert(!dns_query_valid(query,11)); query[2]=0x80; assert(!dns_query_valid(query,12));
    const uint32_t bad_resolvers[]={0,0xffffffff,0x7f000001,0x00010203,0xe0000001,0xf0000001,0xc0000201,0xc0000202,0x64500001};
    for(size_t i=0;i<sizeof bad_resolvers/sizeof bad_resolvers[0];i++)
        assert(!resolver_is_usable(swap32(bad_resolvers[i])));
    assert(resolver_is_usable(swap32(0x64600001))); /* legitimate CGNAT DNS */
    uint32_t rng=42;
    char input[6000];
    for(int t=0;t<50000;t++) {
        rng=rng*1664525u+1013904223u; size_t length=rng%sizeof input;
        for(size_t j=0;j<length;j++) { rng=rng*1664525u+1013904223u; input[j]=rng>>24; }
        memset(decoded,0xa5,sizeof decoded);
        (void)decode_base64url(input,length,decoded,4096,&n);
        assert(decoded[4096]==0xa5 && decoded[4097]==0xa5);
    }
    puts("PASS: actual PeerAPI IPv4/mapped authorization, LAN/unknown/off denial, canonical base64url bounds, resolver guards, 50000 malformed decodes");
}
'''
with tempfile.TemporaryDirectory(prefix='peer-dns-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(fixture+functions+tests)
    flags = ['-std=c11','-Wall','-Wextra','-Werror']
    if os.environ.get('PEER_DNS_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
