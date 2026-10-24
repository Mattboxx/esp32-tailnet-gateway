"""Actual dynamic-DNS core of main/ddns.c.

Covered: settings validation for DuckDNS (sub-domain lists, token format),
Cloudflare (record name, zone id, token) and custom HTTPS URLs (scheme,
host, credentials before the host, spaces/control/quote/fragment
characters), the update schedule (first update, address change, daily
refresh, 30-minute refresh while the address is unknown, Cloudflare waiting
for the address, exponential back-off capped at an hour, success resetting
it) and request URLs ({ip} placeholder, unknown address, length limits).
HTTPS, providers and the STUN address source are NOT covered.
DDNS_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / 'main/ddns.c').read_text(encoding='utf-8')
core = core.split('/* --- ddns core (begin) --- */', 1)[1].split('/* --- ddns core (end) --- */', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ddns.h"
''' + core + r'''
static ddns_config_t duck(void){ddns_config_t c;memset(&c,0,sizeof c);c.provider=DDNS_DUCKDNS;strcpy(c.name,"myhome");strcpy(c.token,"a7c4d2e1-0b3f-4c5d-9e8f-1234567890ab");return c;}
static ddns_config_t cf(void){ddns_config_t c;memset(&c,0,sizeof c);c.provider=DDNS_CLOUDFLARE;strcpy(c.name,"home.example.com");
    strcpy(c.zone,"0123456789abcdef0123456789abcdef");strcpy(c.token,"AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-AbCd");return c;}
static ddns_config_t custom(const char *u){ddns_config_t c;memset(&c,0,sizeof c);c.provider=DDNS_CUSTOM;strcpy(c.url,u);return c;}
static bool ok(ddns_config_t c){char why[120]="";bool v=ddns_config_valid(&c,why,sizeof why);assert(v||why[0]);return v;}
#define IP(a,b,c,d) ((uint32_t)(a)|(uint32_t)(b)<<8|(uint32_t)(c)<<16|(uint32_t)(d)<<24)

int main(void){
    ddns_config_t off;memset(&off,0,sizeof off);assert(ok(off)&&!ddns_config_valid(NULL,NULL,0));
    /* DuckDNS. */
    assert(ok(duck()));
    ddns_config_t c=duck();strcpy(c.name,"home,cabin-2,x");assert(ok(c));
    const char *bad_names[]={"","Home","home.duckdns.org","-home","home-","home,,cabin","a,b,c,d,e,f","ho me","home,"};
    for(unsigned i=0;i<sizeof bad_names/sizeof *bad_names;i++){c=duck();strcpy(c.name,bad_names[i]);assert(!ok(c));}
    const char *bad_tokens[]={"","a7c4d2e1-0b3f-4c5d-9e8f-1234567890a","a7c4d2e1-0b3f-4c5d-9e8f-1234567890abc","a7c4d2e10b3f-4c5d-9e8f-1234567890ab-",
        "A7C4D2E1-0B3F-4C5D-9E8F-1234567890AB","a7c4d2e1-0b3f-4c5d-9e8f-1234567890ag"};
    for(unsigned i=0;i<sizeof bad_tokens/sizeof *bad_tokens;i++){c=duck();strcpy(c.token,bad_tokens[i]);assert(!ok(c));}
    /* Cloudflare. */
    assert(ok(cf()));
    c=cf();strcpy(c.name,"*.example.com");assert(ok(c));
    const char *bad_hosts[]={"","home","home.","-home.example.com","home-.example.com","ho_me.example.com","home..example.com","a.*.example.com","home.example.com/x"};
    for(unsigned i=0;i<sizeof bad_hosts/sizeof *bad_hosts;i++){c=cf();strcpy(c.name,bad_hosts[i]);assert(!ok(c));}
    c=cf();strcpy(c.zone,"0123456789abcdef0123456789abcde");assert(!ok(c));strcpy(c.zone,"0123456789abcdef0123456789abcdeg");assert(!ok(c));
    c=cf();strcpy(c.token,"short");assert(!ok(c));strcpy(c.token,"AbCdEfGhIjKlMnOpQrStUvWxYz0123456789 AbCd");assert(!ok(c));
    /* Custom URL. */
    assert(ok(custom("https://dynv6.com/api/update?hostname=x.dynv6.net&token=t&ipv4={ip}")));
    assert(ok(custom("https://example.org:8443/nic/update")));
    const char *bad_urls[]={"http://example.org/u","https://","https:///x","https://user:pw@example.org/u","https://exa mple.org/",
        "https://example.org/u?a=\"b\"","https://example.org/u#frag","https://example.org/\x01","https://localhost/u","https://*.example.org/u",
        "ftp://example.org"};
    for(unsigned i=0;i<sizeof bad_urls/sizeof *bad_urls;i++)assert(!ok(custom(bad_urls[i])));
    assert(ok(custom("https://example.org/u?user=a@b.c")));                     /* @ after the host is fine */
    c=duck();c.provider=9;assert(!ok(c));

    /* Schedule. */
    ddns_state_t st;memset(&st,0,sizeof st);
    uint32_t a=IP(203,0,113,7),b=IP(198,51,100,9);
    assert(!ddns_due(&st,DDNS_OFF,a,100));
    assert(ddns_due(&st,DDNS_DUCKDNS,0,100));                                   /* first update, address unknown */
    assert(!ddns_due(&st,DDNS_CLOUDFLARE,0,100)&&ddns_due(&st,DDNS_CLOUDFLARE,a,100));   /* Cloudflare needs the address */
    ddns_result(&st,true,a,100);
    assert(st.ever&&st.last_ip==a&&!st.backoff_s);
    assert(!ddns_due(&st,DDNS_CLOUDFLARE,b,120));                               /* at most one a minute */
    assert(ddns_due(&st,DDNS_CLOUDFLARE,b,160)&&!ddns_due(&st,DDNS_CLOUDFLARE,a,160));   /* changed vs same */
    assert(!ddns_due(&st,DDNS_DUCKDNS,a,100+DDNS_REFRESH_S-1)&&ddns_due(&st,DDNS_DUCKDNS,a,100+DDNS_REFRESH_S));
    assert(!ddns_due(&st,DDNS_DUCKDNS,0,100+DDNS_BLIND_S-1)&&ddns_due(&st,DDNS_DUCKDNS,0,100+DDNS_BLIND_S));
    ddns_result(&st,true,0,5000);assert(st.last_ip==a);                         /* unknown address keeps the last one */
    /* Back-off: 60, 120, 240 ... capped at an hour; success resets it. */
    uint32_t now=10000,expect=60;
    for(int i=0;i<10;i++){ddns_result(&st,false,b,now);assert(st.backoff_s==expect&&st.next_try_s==now+expect);
        assert(!ddns_due(&st,DDNS_CLOUDFLARE,b,now+expect-1)&&ddns_due(&st,DDNS_CLOUDFLARE,b,now+expect));
        now+=expect;expect=expect*2>DDNS_BACKOFF_MAX_S?DDNS_BACKOFF_MAX_S:expect*2;}
    assert(st.backoff_s==DDNS_BACKOFF_MAX_S&&st.last_ip==a);                    /* failures never record the address */
    ddns_result(&st,true,b,now);assert(!st.backoff_s&&st.last_ip==b);

    /* Request URLs. */
    char url[320];
    c=duck();assert(ddns_build_url(&c,a,url,sizeof url)&&!strcmp(url,"https://www.duckdns.org/update?domains=myhome&token=a7c4d2e1-0b3f-4c5d-9e8f-1234567890ab&ip=203.0.113.7"));
    assert(ddns_build_url(&c,0,url,sizeof url)&&!strcmp(url+strlen(url)-4,"&ip="));   /* DuckDNS sees the source address */
    assert(!ddns_build_url(&c,a,url,40));
    c=custom("https://e.org/u?ip={ip}&x=1");assert(ddns_build_url(&c,b,url,sizeof url)&&!strcmp(url,"https://e.org/u?ip=198.51.100.9&x=1"));
    assert(!ddns_build_url(&c,0,url,sizeof url));                               /* {ip} needs the address */
    c=custom("https://e.org/u?a={ip}&b={ip}");assert(!ddns_build_url(&c,b,url,sizeof url));   /* one placeholder */
    c=custom("https://e.org/u");assert(ddns_build_url(&c,0,url,sizeof url)&&!strcmp(url,"https://e.org/u"));
    c=cf();assert(!ddns_build_url(&c,a,url,sizeof url));                        /* Cloudflare uses its API */
    puts("ddns core: ok");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='ddns-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'ddns.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('ddns.exe' if os.name == 'nt' else 'ddns')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('DDNS_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'ddns.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
