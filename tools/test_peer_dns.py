"""Compile actual PeerAPI authorization/decoder/resolver guards and the
minimal DoH HTTP request parser (3.0.7-beta.9) with fixtures.

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
parser = '/* One request parsed from the start of a connection buffer.' + source.split('/* One request parsed from the start of a connection buffer.', 1)[1].split('#ifndef PEER_DNS_HOST_TEST', 1)[0]
assert '#include "esp_http_server.h"' not in source and 'httpd_' not in source, 'the framework server is gone'
assert 'if (fd >= 0 && !peer_fd_allowed(fd)) {   /* nothing is read from others */' in source
assert 'if (!peer_fd_allowed(fd)) return respond_error(fd, "403 Forbidden", "forbidden");' in source
fixture = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <strings.h>
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
#include "sockaddr_ipv4.h"
static bool active=true,connected=true,have_instance=true,socket_error;
static uint32_t own_ip=0x64500001, peer_ip=0x64500002;
static struct sockaddr_storage local_address,remote_address;
static bool tailscale_exit_server_active(void) { return active; }
static microlink_t ml;
static microlink_t *tailscale_get_microlink(void) { return have_instance?&ml:NULL; }
static bool microlink_is_connected(microlink_t *m) { (void)m; return connected; }
static uint32_t microlink_get_vpn_ip(microlink_t *m) { (void)m; return own_ip; }
#define PEER_DNS_MAX_QUERY_STRING (PEER_DNS_MAX_B64 + 32U)
#define PEER_DNS_HEAD_MAX (PEER_DNS_MAX_QUERY_STRING + 512U)
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
    for(int i=0;i<2;i++) {
        int family=i?AF_INET6:AF_INET;
        address(&local_address,family,own_ip); address(&remote_address,family,peer_ip);
        assert(peer_fd_allowed(socket_error?-1:4));
        address(&local_address,family,sta.ip); assert(!peer_fd_allowed(socket_error?-1:4));
        address(&local_address,family,own_ip);
        address(&remote_address,family,0x64500003); assert(!peer_fd_allowed(socket_error?-1:4));
        address(&remote_address,family,peer_ip);
        active=false; assert(!peer_fd_allowed(socket_error?-1:4)); active=true;
        connected=false; assert(!peer_fd_allowed(socket_error?-1:4)); connected=true;
        have_instance=false; assert(!peer_fd_allowed(socket_error?-1:4)); have_instance=true;
        socket_error=true; assert(!peer_fd_allowed(socket_error?-1:4)); socket_error=false;
    }
    ((struct sockaddr_in6*)&remote_address)->sin6_addr.s6_addr[0]=0x20;
    assert(!peer_fd_allowed(socket_error?-1:4));
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
    /* Minimal DoH HTTP parser. */
    peer_request_t r;
    #define P(text) parse_request((const uint8_t *)(text), strlen(text), &r)
    P("GET /dns-query?dns=AAEBAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE HTTP/1.1\r\nHost: x\r\n\r\n");
    assert(r.kind == PEER_REQ_GET && !r.close && r.query_len == 43 && !memcmp(r.query, "dns=", 4));
    assert(r.consumed == strlen("GET /dns-query?dns=AAEBAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE HTTP/1.1\r\nHost: x\r\n\r\n"));
    uint8_t q[4096]; size_t ql = 0;
    assert(get_query(r.query, r.query_len, q, &ql) && ql == 29 && q[0] == 0 && q[1] == 1 && q[2] == 1 && !memcmp(q + 13, "example", 7));
    assert(!get_query("dns=AA&dns=AA", 13, q, &ql));                 /* duplicate */
    assert(!get_query("x=1", 3, q, &ql) && !get_query("dns=", 4, q, &ql));
    P("GET /dns-query?dns=AAAB HTTP/1.0\r\n\r\n"); assert(r.kind == PEER_REQ_GET && r.close);
    P("GET /dns-query?x HTTP/1.1\r\nConnection: keep-alive, Close\r\n\r\n"); assert(r.kind == PEER_REQ_GET && r.close);
    P("GET /dns-query HTTP/1.1\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);      /* GET needs a query */
    P("GET /dns-queryX?dns=AA HTTP/1.1\r\n\r\n"); assert(r.kind == PEER_REQ_NOT_FOUND);
    P("GET / HTTP/1.1\r\n\r\n"); assert(r.kind == PEER_REQ_NOT_FOUND && r.close);
    P("PUT /dns-query HTTP/1.1\r\n\r\n"); assert(r.kind == PEER_REQ_METHOD);
    P("get /dns-query?dns=AA HTTP/1.1\r\n\r\n"); assert(r.kind == PEER_REQ_METHOD);
    P("GET /dns-query?dns=AA HTTP/2.0\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("GET /dns-query?dns=AA HTTP/1.1\r\n"); assert(r.kind == PEER_REQ_INCOMPLETE);
    P("GET /dns-query?dns=AA HTTP/1.1\r\nBad header\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("GET /dns-query?dns=AA HTTP/1.1\r\nA: 1\r\n folded\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("GET /dns-query?dns=AA HTTP/1.1\r\nContent-Length: 3\r\n\r\nabc"); assert(r.kind == PEER_REQ_BAD);
    P("GET /dns-query?dns=AA HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    /* POST: media type, length bounds, partial body, pipelining. */
    char post[256];
    snprintf(post, sizeof post, "POST /dns-query HTTP/1.1\r\nContent-Type: Application/DNS-Message; x=1\r\nContent-Length: 12\r\n\r\n%s", "abcdefghijkl");
    P(post); assert(r.kind == PEER_REQ_POST && r.body_len == 12 && !memcmp(r.body, "abcdefghijkl", 12) && r.consumed == strlen(post) && !r.close);
    parse_request((const uint8_t *)post, strlen(post) - 1, &r); assert(r.kind == PEER_REQ_INCOMPLETE);
    char two[600]; snprintf(two, sizeof two, "%s%s", post, post);
    P(two); assert(r.kind == PEER_REQ_POST && r.consumed == strlen(post));
    parse_request((const uint8_t *)two + r.consumed, strlen(two) - r.consumed, &r); assert(r.kind == PEER_REQ_POST);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\nabcdefghijkl"); assert(r.kind == PEER_REQ_MEDIA);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 11\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 4097\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 999999\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 1x\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    P("POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 12\r\nContent-Length: 12\r\n\r\n"); assert(r.kind == PEER_REQ_BAD);
    /* Limits: a header section that never ends is refused at the bound, NUL bytes too. */
    static uint8_t big[PEER_DNS_HEAD_MAX + 64];
    memset(big, 'a', sizeof big); memcpy(big, "GET /dns-query?dns=", 19);
    parse_request(big, PEER_DNS_HEAD_MAX - 1, &r); assert(r.kind == PEER_REQ_INCOMPLETE);
    parse_request(big, PEER_DNS_HEAD_MAX, &r); assert(r.kind == PEER_REQ_TOO_LARGE);
    const char nul[] = "GET /dns-query?dns=AA\0 HTTP/1.1\r\n\r\n";
    parse_request((const uint8_t *)nul, sizeof nul - 1, &r); assert(r.kind == PEER_REQ_BAD);
    /* Random input: never reads outside the buffer, consumed within length. */
    for (int t = 0; t < 200000; t++) {
        rng = rng * 1664525u + 1013904223u; size_t length = 1 + rng % 300;
        uint8_t *in = malloc(length);
        const char *seed = (rng >> 8) & 1 ? "POST /dns-query HTTP/1.1\r\nContent-Type: application/dns-message\r\nContent-Length: 12\r\n\r\n"
                                           : "GET /dns-query?dns=AA HTTP/1.1\r\n\r\n";
        size_t keep = strlen(seed) < length ? strlen(seed) : length;
        memcpy(in, seed, keep);
        for (size_t j = keep; j < length; j++) { rng = rng * 1664525u + 1013904223u; in[j] = rng >> 24; }
        rng = rng * 1664525u + 1013904223u;
        if (keep > 4) in[rng % keep] = (uint8_t)(rng >> 24);   /* corrupt one byte of the seed */
        parse_request(in, length, &r);
        assert(r.consumed <= length);
        if (r.kind == PEER_REQ_POST) assert(r.body >= in && r.body + r.body_len <= in + length);
        if (r.kind == PEER_REQ_GET) assert((const uint8_t *)r.query >= in && (const uint8_t *)r.query + r.query_len <= in + length);
        free(in);
    }
    puts("PASS: actual PeerAPI IPv4/mapped authorization, LAN/unknown/off denial, canonical base64url bounds, resolver guards, "
         "50000 malformed decodes; DoH request parser (GET/POST, keep-alive/close, 404/405/415/431/400 cases, length and header "
         "bounds, pipelining, partial input, 200000 mutated requests)");
}
'''
with tempfile.TemporaryDirectory(prefix='peer-dns-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(fixture+functions+parser+tests)
    flags = ['-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'main')]
    if os.environ.get('PEER_DNS_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary = path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
