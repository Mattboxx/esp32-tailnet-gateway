"""Exercise the actual network refresh and SNMP traffic hooks together.

No network/device access. The dev.10 crash arose only with both installers:
isolated idempotence tests missed the alternating refresh cycle. Enable
NETIF_SANITIZE=1 on Linux for ASan/UBSan.
"""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-ref', help='Replay the same regression against a Git revision')
args = parser.parse_args()
source = (subprocess.check_output(['git', 'show', args.source_ref + ':main/netif_hooks.c'],
          cwd=ROOT, text=True) if args.source_ref else
          (ROOT / 'main/netif_hooks.c').read_text(encoding='utf-8'))
# Include the old installer too when replaying this test against dev.10.
start = 'static err_t wg_input_hook' if 'static err_t wg_input_hook' in source else 'void netif_hooks_refresh'
functions = start + source.split(start, 1)[1].split('void netif_hooks_init', 1)[0]
snmp = (ROOT / 'components/snmp_agent/snmp_agent.c').read_text(encoding='utf-8')
app = (ROOT / 'main/main.c').read_text(encoding='utf-8')
assert app.index('netif_hooks_init();') < app.index('snmp_agent_init();'), \
    'Physical ACL hooks must be installed once before the periodic SNMP hooks'
hooks = '#define DEFINE_IF_HOOKS' + snmp.split('#define DEFINE_IF_HOOKS', 1)[1].split(
    '/* Re-scan for interfaces worth counting.', 1)[0]

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
typedef int err_t;
#define ERR_OK 0
#define ERR_VAL -1
typedef struct { uint32_t addr; } ip4_addr_t;
struct pbuf { uint16_t tot_len; bool freed; };
struct netif;
typedef err_t (*netif_input_fn)(struct pbuf *, struct netif *);
typedef err_t (*netif_linkoutput_fn)(struct netif *, struct pbuf *);
typedef err_t (*netif_output_fn)(struct netif *, struct pbuf *, const ip4_addr_t *);
struct netif {
    struct netif *next; char name[2]; uint8_t num; ip4_addr_t ip;
    netif_input_fn input; netif_linkoutput_fn linkoutput; netif_output_fn output;
};
static struct netif *netif_list, *hooked_wg;
static netif_input_fn original_wg_input;
#define netif_ip4_addr(n) (&(n)->ip)
#define ip4_addr_isany_val(a) ((a).addr == 0)
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
static bool queue_fails;
static err_t tcpip_try_callback(void (*callback)(void *), void *arg) {
    if(queue_fails) return ERR_VAL;
    callback(arg); return ERR_OK;
}
typedef struct {
    uint32_t rx_octets, rx_pkts, tx_octets, tx_pkts;
    netif_input_fn orig_input;
    netif_linkoutput_fn orig_linkoutput;
    netif_output_fn orig_output;
} iftraf_t;
#define IF_ETH 0
#define IF_WIFI 1
#define IF_TS 2
#define IF_SLOTS 3
static iftraf_t s_traf[IF_SLOTS];
static unsigned input_calls, output_calls;
static err_t driver_input(struct pbuf *p, struct netif *n) {
    assert(n && !p->freed); ++input_calls; return 42;
}
static err_t driver_linkoutput(struct netif *n, struct pbuf *p) {
    assert(n && !p->freed); ++output_calls; return 24;
}
static err_t driver_output(struct netif *n, struct pbuf *p, const ip4_addr_t *a) {
    assert(n && a && !p->freed); ++output_calls; return 24;
}
/* These represent the once-installed physical ACL chain, not the tunnel. */
static err_t physical_acl_input(struct pbuf *p, struct netif *n) { return driver_input(p,n); }
static err_t physical_acl_output(struct netif *n, struct pbuf *p) { return driver_linkoutput(n,p); }
'''

tests = r'''
int main(void) {
    struct pbuf p={.tot_len=64};
    struct netif sta={.name={'s','t'},.ip={swap32(0x64400002)},
        .input=physical_acl_input,.linkoutput=physical_acl_output};
    struct netif eth={.name={'e','n'},.ip={swap32(0x647ffffe)},
        .input=driver_input,.linkoutput=driver_linkoutput};
    struct netif ap={.name={'a','p'},.ip={swap32(0x64500002)},.input=driver_input};
    struct netif wg={.name={'w','g'},.ip={swap32(0x64500003)},
        .input=driver_input,.output=driver_output};
    netif_list=&sta; sta.next=&eth; eth.next=&ap; ap.next=&wg;
    netif_hooks_refresh();
    assert(sta.input==physical_acl_input && eth.input==driver_input && ap.input==driver_input);
    for(unsigned cycle=0;cycle<20;cycle++) {
        /* Recreate the tunnel in the same allocation, as on reconnect. */
        wg.input=driver_input; wg.output=driver_output;
        for(unsigned i=0;i<200;i++) {
            netif_hooks_refresh();
            hook_netif(IF_TS,&wg); hook_netif(IF_WIFI,&sta); hook_netif(IF_ETH,&eth);
            netif_hooks_refresh();
            /* Fail before invoking a recursive chain, even on the old code. */
            assert(s_traf[IF_TS].orig_input==driver_input);
            assert(s_traf[IF_WIFI].orig_input==physical_acl_input);
            unsigned rx=input_calls,tx=output_calls;
            uint32_t counted=s_traf[IF_TS].rx_pkts;
            assert(wg.input(&p,&wg)==42 && input_calls==rx+1);
            assert(s_traf[IF_TS].rx_pkts==counted+1);
            assert(wg.output(&wg,&p,&wg.ip)==24 && output_calls==tx+1);
            assert(sta.input(&p,&sta)==42);
            assert(sta.linkoutput(&sta,&p)==24);
            assert(eth.input(&p,&eth)==42);
            assert(eth.linkoutput(&eth,&p)==24);
            assert(!p.freed);
        }
        unhook_netif(IF_TS,&wg); unhook_netif(IF_WIFI,&sta); unhook_netif(IF_ETH,&eth);
        assert(wg.input==driver_input && wg.output==driver_output);
        assert(sta.input==physical_acl_input && sta.linkoutput==physical_acl_output);
        hook_netif(IF_TS,&wg); netif_hooks_refresh(); hook_netif(IF_TS,&wg);
        assert(s_traf[IF_TS].orig_input==driver_input && wg.input(&p,&wg)==42);
        unhook_netif(IF_TS,&wg);
    }
    puts("PASS: actual SNMP/network installers together; 4000 alternating refreshes; exact-once RX/TX; physical ACL chain, reconnect/address reuse and 20 disable/enable cycles preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='netif-hooks-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + functions + hooks + tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable']
    if os.environ.get('NETIF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
