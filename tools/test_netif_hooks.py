"""Run actual tunnel hook discovery/input with synthetic lwIP interfaces.

No device or network access. NETIF_SANITIZE=1 enables ASan/UBSan in CI.
The pinned WireGuard driver names its interface 'wg'; a CGNAT address alone
must never turn a physical uplink or AP into a raw-IP tunnel input.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/netif_hooks.c').read_text(encoding='utf-8')
functions = 'static err_t wg_input_hook' + source.split(
    'static err_t wg_input_hook', 1)[1].split('void netif_hooks_init', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
typedef int err_t;
#define ERR_OK 0
#define ERR_VAL -1
typedef struct { uint32_t addr; } ip4_addr_t;
struct pbuf { bool freed; };
struct netif;
typedef err_t (*netif_input_fn)(struct pbuf *, struct netif *);
struct netif { struct netif *next; char name[2]; uint8_t num; ip4_addr_t ip; netif_input_fn input; };
static struct netif *netif_list, *hooked_wg;
static netif_input_fn original_wg_input;
#define netif_ip4_addr(n) (&(n)->ip)
#define ip4_addr_isany_val(a) ((a).addr == 0)
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
static bool denied, queue_fails;
static unsigned raw_calls, physical_calls, filter_calls, frees;
static struct netif *expected_raw;
static bool tailnet_forward_allow_non_uplink_packet(struct pbuf *p, bool ethernet, uint32_t local_ip) {
    assert(p && !p->freed && !ethernet && expected_raw && local_ip==expected_raw->ip.addr); ++filter_calls; return !denied;
}
static void pbuf_free(struct pbuf *p) { assert(!p->freed); p->freed=true; ++frees; }
static err_t raw_input(struct pbuf *p, struct netif *n) {
    assert(!p->freed && n==expected_raw); ++raw_calls; return 42;
}
static err_t physical_input(struct pbuf *p, struct netif *n) {
    assert(!p->freed && n!=expected_raw); ++physical_calls; return 24;
}
static err_t tcpip_try_callback(void (*callback)(void *), void *arg) {
    if(queue_fails) return ERR_VAL;
    callback(arg); return ERR_OK;
}
'''
tests = r'''
int main(void) {
    struct netif sta={.name={'s','t'},.ip={swap32(0x64400002)},.input=physical_input};
    struct netif ap={.name={'a','p'},.ip={swap32(0x64500002)},.input=physical_input};
    struct netif eth={.name={'e','n'},.ip={swap32(0x647ffffe)},.input=physical_input};
    sta.next=&ap; ap.next=&eth; netif_list=&sta;
    netif_hooks_refresh();
    assert(sta.input==physical_input && ap.input==physical_input && eth.input==physical_input);
    assert(!hooked_wg && !original_wg_input);
    struct pbuf p={0}; assert(sta.input(&p,&sta)==24 && physical_calls==1 && filter_calls==0);

    /* The real tunnel appears later, after DHCP and initial refreshes. */
    struct netif wg={.name={'w','g'},.input=raw_input};
    expected_raw=&wg; eth.next=&wg;
    netif_hooks_refresh(); assert(wg.input==raw_input && !hooked_wg);
    wg.ip.addr=swap32(0xc0000201); netif_hooks_refresh(); assert(wg.input==raw_input);
    wg.ip.addr=swap32(0x64500003);
    queue_fails=true; netif_hooks_refresh(); assert(wg.input==raw_input); queue_fails=false;
    netif_hooks_refresh();
    assert(hooked_wg==&wg && original_wg_input==raw_input && wg.input==wg_input_hook);
    assert(sta.input==physical_input && ap.input==physical_input && eth.input==physical_input);
    for(unsigned i=0;i<20;i++) netif_hooks_refresh();
    assert(original_wg_input==raw_input); /* no self-wrapping / recursion */
    assert(wg.input(&p,&wg)==42 && raw_calls==1 && filter_calls==1 && !p.freed);
    denied=true; assert(wg.input(&p,&wg)==ERR_OK && p.freed && frees==1 && raw_calls==1);
    p.freed=false; denied=false;
    original_wg_input=NULL; assert(wg.input(&p,&wg)==ERR_VAL && !p.freed);
    original_wg_input=raw_input;
    /* List ordering cannot change the physical interfaces' input chains. */
    eth.next=NULL; wg.next=&sta; netif_list=&wg;
    netif_hooks_refresh(); assert(wg.input(&p,&wg)==42 && raw_calls==2);
    assert(sta.input(&p,&sta)==24 && physical_calls==2);
    assert(ap.input==physical_input && eth.input==physical_input);
    puts("PASS: actual netif hook discovery rejects CGNAT STA/AP/Ethernet; delayed WG, queue failure, idempotence, raw input/filter/drop and list ordering");
}
'''
with tempfile.TemporaryDirectory(prefix='netif-hooks-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + functions + tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('NETIF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
