"""Actual Ethernet uplink core: pin/IP validation, uplink selection, record load.

Compiles the real core and record loader of main/eth_uplink.c with fixture NVS.
No SPI, PHY, driver or network. Physical W5500 behavior is NOT covered.
ETH_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/eth_uplink.c').read_text(encoding='utf-8')
header = (ROOT / 'main/eth_uplink.h').read_text(encoding='utf-8')
types = 'enum {ETH_CHIP_W5500' + header.split('enum {ETH_CHIP_W5500', 1)[1].split('bool eth_config_valid', 1)[0]
core = source.split('/* --- eth core (begin) --- */', 1)[1].split('/* --- eth core (end) --- */', 1)[0]
record = '#define ETH_MAGIC' + source.split('#define ETH_MAGIC', 1)[1].split('static void ensure_lock', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define NVS_READONLY 0
#define NVS_NAMESPACE "tsr"
typedef int nvs_handle_t;typedef void *SemaphoreHandle_t;typedef int StaticSemaphore_t;typedef struct esp_netif esp_netif_t;struct netif;
static uint32_t ntohl(uint32_t x){return __builtin_bswap32(x);}
static uint32_t ip4(int a,int b,int c,int d){return __builtin_bswap32((uint32_t)a<<24|(uint32_t)b<<16|(uint32_t)c<<8|(uint32_t)d);}
''' + types + 'bool eth_config_valid(const eth_config_t *c, char *why, size_t why_size);\n' + core + r'''
static unsigned char blob[256];static size_t blob_size;static int open_fail;
static esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h){(void)ns;(void)mode;*h=1;return open_fail?ESP_FAIL:ESP_OK;}
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *k,void *out,size_t *n){(void)h;assert(!strcmp(k,"eth_cfg"));if(!blob_size)return ESP_FAIL;if(*n<blob_size){*n=blob_size;return ESP_FAIL;}memcpy(out,blob,blob_size);*n=blob_size;return ESP_OK;}
static void nvs_close(nvs_handle_t h){(void)h;}
''' + record + r'''
static eth_config_t good(void){eth_config_t c;defaults(&c);c.enabled=1;return c;}
static bool valid(eth_config_t c){char why[96]="";bool ok=eth_config_valid(&c,why,sizeof why);assert(ok||why[0]);return ok;}
int main(void){
    eth_config_t c=good();assert(valid(c));
    c.enabled=0;assert(valid(c)); /* disabled records are still fully validated */
    int forbidden[]={0,3,19,20,26,30,33,37,38,39,40,43,44,45,46,49,-1,-5,127};
    for(unsigned i=0;i<sizeof forbidden/sizeof *forbidden;i++){c=good();c.sclk=(int8_t)forbidden[i];assert(!valid(c));}
    c=good();c.intr=-1;c.rst=-1;assert(valid(c)); /* polling mode, no reset line */
    c=good();c.intr=-2;assert(!valid(c));
    c=good();c.cs=c.mosi;assert(!valid(c));c=good();c.rst=c.intr;assert(!valid(c));
    c=good();c.chip=2;assert(!valid(c));c=good();c.spi_host=0;assert(!valid(c));c=good();c.spi_host=3;assert(!valid(c));
    c=good();c.spi_mhz=0;assert(!valid(c));c.spi_mhz=41;assert(!valid(c));c.spi_mhz=40;assert(valid(c));
    c=good();c.preference=2;assert(!valid(c));c=good();c.enabled=2;assert(!valid(c));c=good();c.ip_static=2;assert(!valid(c));
    eth_config_t s=good();s.ip_static=1;s.ip=ip4(192,168,1,50);s.mask=ip4(255,255,255,0);s.gw=ip4(192,168,1,1);assert(valid(s));
    c=s;c.mask=ip4(255,0,255,0);assert(!valid(c));c=s;c.mask=0;assert(!valid(c));c=s;c.mask=0xffffffffu;assert(!valid(c));
    c=s;c.ip=ip4(192,168,1,0);assert(!valid(c));c=s;c.ip=ip4(192,168,1,255);assert(!valid(c));
    c=s;c.ip=ip4(127,0,0,5);c.gw=ip4(127,0,0,1);c.mask=ip4(255,0,0,0);assert(!valid(c));c=s;c.ip=ip4(224,0,0,5);assert(!valid(c));
    c=s;c.gw=ip4(10,0,0,1);assert(!valid(c));c=s;c.gw=c.ip;assert(!valid(c));c=s;c.gw=0;assert(!valid(c));
    c=s;c.ip_static=0;c.ip=0;assert(valid(c)); /* DHCP ignores static fields */
    assert(!eth_config_valid(NULL,NULL,0));

    /* Selection: disabled is legacy; wifi_first falls back only when STA lacks an address. */
    eth_selector_t sel={0};
    assert(eth_uplink_choose(&sel,false,ETH_PREF_ETHERNET_FIRST,false,true)==ETH_CHOICE_LEGACY&&!sel.eth_streak);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_WIFI_FIRST,true,true)==ETH_CHOICE_STA);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_WIFI_FIRST,false,true)==ETH_CHOICE_ETH);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_WIFI_FIRST,false,false)==ETH_CHOICE_STA);
    /* ethernet_first waits for ETH_STABLE_SAMPLES before leaving a working STA, drops back at once. */
    sel=(eth_selector_t){0};
    for(int i=1;i<ETH_STABLE_SAMPLES;i++)assert(eth_uplink_choose(&sel,true,ETH_PREF_ETHERNET_FIRST,true,true)==ETH_CHOICE_STA);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_ETHERNET_FIRST,true,true)==ETH_CHOICE_ETH);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_ETHERNET_FIRST,true,false)==ETH_CHOICE_STA&&!sel.eth_streak);
    assert(eth_uplink_choose(&sel,true,ETH_PREF_ETHERNET_FIRST,false,true)==ETH_CHOICE_ETH); /* no STA: use ETH now */
    for(int i=0;i<300;i++){eth_uplink_choose(&sel,true,ETH_PREF_ETHERNET_FIRST,true,true);}
    assert(sel.eth_streak==ETH_STABLE_SAMPLES); /* saturates */

    /* Record load: only a checksummed, valid v1 record is used; anything else is OFF. */
    eth_config_t out;eth_record_t r={.magic=ETH_MAGIC,.version=1,.config=s};r.checksum=record_checksum(&r);
    memcpy(blob,&r,sizeof r);blob_size=sizeof r;load(&out);assert(!memcmp(&out,&s,sizeof s));
    eth_record_t bad=r;bad.checksum^=1;memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    bad=r;bad.version=2;bad.checksum=record_checksum(&bad);memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    bad=r;bad.config.sclk=33;bad.checksum=record_checksum(&bad);memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled); /* valid checksum, unsafe pins */
    blob_size=sizeof r-1;memcpy(blob,&r,sizeof r);load(&out);assert(!out.enabled);
    blob_size=0;load(&out);assert(!out.enabled);open_fail=1;blob_size=sizeof r;load(&out);assert(!out.enabled);
    puts("PASS: actual Ethernet pin/SPI/static-IP validation, wifi_first/ethernet_first selection with stability window, fail-closed record load (no hardware)");
}
'''

with tempfile.TemporaryDirectory(prefix='eth-uplink-') as folder:
    path = Path(folder); (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable']
    if os.environ.get('ETH_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)

# Second program: actual POST /api/ethernet parser with the real validation core.
def function(text, signature):
    at = text.index(signature); return text[at:text.index('\n}', at) + 2] + '\n'
HTTP = r'''
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "json_guard.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
#define AF_INET 2
#define HTTPD_400_BAD_REQUEST 400
typedef struct {int content_len,offset,status;const char *body;bool authorized;char reply[256];} httpd_req_t;
struct in_addr {uint32_t s_addr;};
static uint32_t ntohl(uint32_t x){return __builtin_bswap32(x);}
static int inet_pton(int af,const char *s,void *dst){(void)af;unsigned a,b,c,d;char tail;if(sscanf(s,"%u.%u.%u.%u%c",&a,&b,&c,&d,&tail)!=4||a>255||b>255||c>255||d>255)return 0;
  ((struct in_addr*)dst)->s_addr=__builtin_bswap32(a<<24|b<<16|c<<8|d);return 1;}
static const char *esp_err_to_name(esp_err_t e){(void)e;return "ESP_FAIL";}
static int web_ui_require_auth(httpd_req_t *r){if(r->authorized)return ESP_OK;r->status=401;return ESP_FAIL;}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);}
static void httpd_resp_send_err(httpd_req_t *r,int s,const char *m){(void)m;r->status=s;}
static void httpd_resp_send_408(httpd_req_t *r){r->status=408;}
static void httpd_resp_send_500(httpd_req_t *r){r->status=500;}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;}
static void httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){(void)r;(void)k;(void)v;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){snprintf(r->reply,sizeof r->reply,"%s",s);if(!r->status)r->status=200;return ESP_OK;}
static int httpd_req_recv(httpd_req_t *r,char *out,int n){memcpy(out,r->body+r->offset,n);r->offset+=n;return n;}
''' + types + 'bool eth_config_valid(const eth_config_t *c, char *why, size_t why_size);\n' + core + r'''
static eth_config_t stored;static int saves;static esp_err_t save_result;
static esp_err_t eth_uplink_set_config(const eth_config_t *c,char *why,size_t n){if(!eth_config_valid(c,why,n))return ESP_ERR_INVALID_ARG;saves++;if(save_result)return save_result;stored=*c;return ESP_OK;}
''' + ''.join(function(source, s) for s in ('static esp_err_t send_json(', 'static bool json_int(', 'static bool json_ip(', 'static esp_err_t post_ethernet(')) + r'''
static httpd_req_t post(const char *body){httpd_req_t r={.content_len=(int)strlen(body),.body=body,.authorized=true};post_ethernet(&r);return r;}
#define PINS "\"spi_mhz\":20,\"sclk\":12,\"mosi\":11,\"miso\":13,\"cs\":10,\"int\":14,\"rst\":9,\"dns\":\"\""
#define BASE "\"chip\":\"w5500\",\"spi_host\":2," PINS
#define DHCP ",\"static_ip\":false,\"ip\":\"\",\"netmask\":\"\",\"gateway\":\"\"}"
int main(void){
    httpd_req_t r=post("{\"enabled\":true," BASE ",\"preference\":\"ethernet_first\",\"static_ip\":true,\"ip\":\"192.168.1.60\",\"netmask\":\"255.255.255.0\",\"gateway\":\"192.168.1.1\"}");
    assert(r.status==200&&strstr(r.reply,"restart_required")&&stored.enabled&&stored.spi_host==1&&stored.preference==ETH_PREF_ETHERNET_FIRST&&stored.ip_static&&ntohl(stored.ip)==0xc0a8013c);
    r=post("{\"enabled\":false," BASE ",\"preference\":\"wifi_first\",\"static_ip\":false,\"ip\":\"10.0.0.5\",\"netmask\":\"\",\"gateway\":\"\"}");
    assert(r.status==200&&!stored.enabled&&!stored.ip&&!stored.mask); /* DHCP clears static fields */
    eth_config_t keep=stored;
    const char *bad[]={
     "{\"enabled\":true,\"chip\":\"w5500\",\"spi_host\":2,\"spi_mhz\":20,\"sclk\":33,\"mosi\":11,\"miso\":13,\"cs\":10,\"int\":14,\"rst\":9,\"dns\":\"\",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":1," BASE ",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":true," BASE ",\"preference\":\"fastest\"" DHCP,
     "{\"enabled\":true," BASE ",\"preference\":\"wifi_first\",\"static_ip\":true,\"ip\":\"192.168.1.60\",\"netmask\":\"255.0.255.0\",\"gateway\":\"192.168.1.1\"}",
     "{\"enabled\":true," BASE ",\"preference\":\"wifi_first\",\"static_ip\":true,\"ip\":\"192.168.1.60\",\"netmask\":\"255.255.255.0\",\"gateway\":\"10.0.0.1\"}",
     "{\"enabled\":true," BASE ",\"preference\":\"wifi_first\",\"static_ip\":true,\"ip\":\"999.1.1.1\",\"netmask\":\"255.255.255.0\",\"gateway\":\"192.168.1.1\"}",
     "{\"enabled\":true,\"chip\":\"dm9051\",\"spi_host\":2," PINS ",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":true,\"chip\":\"w5500\",\"spi_host\":4," PINS ",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":true,\"chip\":\"w5500\",\"spi_host\":2,\"spi_mhz\":20.5,\"sclk\":12,\"mosi\":11,\"miso\":13,\"cs\":10,\"int\":14,\"rst\":9,\"dns\":\"\",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":true,\"chip\":\"w5500\",\"spi_host\":2,\"spi_mhz\":20,\"sclk\":12,\"mosi\":12,\"miso\":13,\"cs\":10,\"int\":14,\"rst\":9,\"dns\":\"\",\"preference\":\"wifi_first\"" DHCP,
     "{\"enabled\":true}","[]","{"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){r=post(bad[i]);assert(r.status==400&&!memcmp(&stored,&keep,sizeof keep));}
    r=post(bad[0]);assert(strstr(r.reply,"pin not usable"));
    save_result=ESP_FAIL;r=post("{\"enabled\":true," BASE ",\"preference\":\"wifi_first\"" DHCP);
    assert(r.status==500&&!memcmp(&stored,&keep,sizeof keep));save_result=ESP_OK;
    httpd_req_t denied={.content_len=2,.body="{}",.authorized=false};int before=saves;post_ethernet(&denied);assert(denied.status==401&&saves==before);
    char big[600];memset(big,' ',sizeof big-1);big[sizeof big-1]=0;r=post(big);assert(r.status==400);
    puts("PASS: actual Ethernet POST: typed fields, real pin/SPI/static-IP validation, DHCP clears static fields, 400/500/401 without saved-state change (fixtures)");
}
'''
with tempfile.TemporaryDirectory(prefix='eth-http-') as folder:
    path = Path(folder); (path / 'http.c').write_text(HTTP, encoding='utf-8')
    binary = path / ('http.exe' if os.name == 'nt' else 'http')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(ROOT / 'main')]
    libs = ['-lm']; dep = os.environ.get('CJSON_SOURCE')
    if dep: flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('ETH_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'http.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
