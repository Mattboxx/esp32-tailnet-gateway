"""Actual forwarding policy/core wrapper with a deterministic lwIP input queue.

No device/network access. TAILNET_SANITIZE=1 enables ASan/UBSan in CI.
The queue/receive-DNAT eligibility model follows the pinned SDK's wlanif_input,
tcpip_input and ip4_input; it is not an end-to-end TCP/UDP or fragment test.
"""
from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/tailnet_forward.c').read_text(encoding='utf-8')
functions='static bool packet_fields'+source.split('static bool packet_fields',1)[1]
policy='int tailnet_forward_snapshot_mappings'+source.split('int tailnet_forward_snapshot_mappings',1)[1].split('static bool packet_fields',1)[0]
conflicts='bool tailnet_forward_listen_conflicts'+source.split('bool tailnet_forward_listen_conflicts',1)[1].split('static bool remove_expired_rules',1)[0]
core_path=ROOT/'main/tailnet_input.c'
cmake=(ROOT/'main/CMakeLists.txt').read_text(encoding='utf-8')
assert '"tailnet_input.c"' in cmake and '"-Wl,--wrap=ip4_input"' in cmake, 'IPv4 policy wrapper must be compiled and linked'
core=core_path.read_text(encoding='utf-8') if core_path.exists() else 'err_t __wrap_ip4_input(struct pbuf *p, struct netif *n) { return __real_ip4_input(p,n); }'
core='\n'.join(line for line in core.splitlines() if not line.startswith('#include'))
early_filter='tailnet_forward_allow_uplink_packet(p,' in (ROOT/'main/netif_hooks.c').read_text(encoding='utf-8')
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int esp_err_t;
#include "tailnet_forward.h"
/* Permanent-lease fixture; standalone actual lease engine has separate tests. */
static bool service_lease_allowed(int i,const tailnet_forward_rule_t *r){(void)i;(void)r;return true;}
typedef int err_t;
#define ERR_OK 0
static int core_depth, lock_depth;
#define LWIP_ASSERT_CORE_LOCKED() assert(core_depth==1)
#define LOCK() do { assert(!lock_depth); ++lock_depth; } while(0)
#define UNLOCK() do { assert(lock_depth==1); --lock_depth; } while(0)
static tailnet_forward_rule_t s_rules[TAILNET_FORWARD_MAX];
static tailnet_forward_runtime_t s_runtime[TAILNET_FORWARD_MAX];
static int s_count;
static uint32_t fixture_uptime_s=1;
#define TF_UPTIME_S() fixture_uptime_s
static uint64_t s_generation=1;
typedef struct { bool installed; tailnet_forward_mapping_t mapping; } active_mapping_t;
static active_mapping_t s_active[TAILNET_FORWARD_MAX];
static size_t strlcpy(char *d,const char *s,size_t z) { size_t n=strlen(s);if(z){size_t c=n<z-1?n:z-1;memcpy(d,s,c);d[c]=0;}return n; }
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define lwip_htonl swap32
#define lwip_ntohs(x) ((uint16_t)(((x)>>8)|((x)<<8)))
#define netif_ip4_addr(n) (&(n)->ip)
#define IP_OFFMASK 0x1fff
static uint16_t pbuf_copy_partial(const struct pbuf *p,void *to,uint16_t length,uint16_t offset) {
    uint16_t copied=0;
    while(p && copied<length) {
        if(offset>=p->len) { offset-=p->len; p=p->next; continue; }
        uint16_t n=p->len-offset; if(n>length-copied)n=length-copied;
        memcpy((uint8_t*)to+copied,(uint8_t*)p->payload+offset,n); copied+=n; offset=0; p=p->next;
    }
    return copied;
}
static unsigned freed, inputs, translated, local_dns;
#define IP_REASSEMBLY 0
#define IP_MF 0x2000
#define PBUF_RAW 0
static void pbuf_realloc(struct pbuf *p,uint16_t length) { assert(length<=p->tot_len);p->tot_len=length;if(p->len>length)p->len=length; }
static struct pbuf *pbuf_coalesce(struct pbuf *p,int layer) { assert(layer==PBUF_RAW);return p; }
void pbuf_free(struct pbuf *p) { assert(core_depth==1 && p); ++freed; }
/* Cellular PPP ACL decision (netif_hooks); denied packets never reach policy or ip4_input. */
static int ppp_deny;
static bool netif_hooks_ppp_input_allowed(struct pbuf *p,struct netif *n){(void)p;(void)n;return !ppp_deny;}
static err_t __real_ip4_input(struct pbuf *p,struct netif *n) {
    assert(core_depth==1); ++inputs;
    uint8_t header[24]; assert(pbuf_copy_partial(p,header,sizeof header,0)==sizeof header);
    uint32_t dest; memcpy(&dest,header+16,4);
    uint16_t port=((uint16_t)header[22]<<8)|header[23];
    /* Exact pinned receive-NAPT eligibility; the injected port map exists
     * after activate(), without another policy check inside the SDK. */
    if(!n->napt && dest==n->ip.addr && s_active[0].installed && port==s_active[0].mapping.rule.listen_port) ++translated;
    else if(n->napt && header[9]==17 && port==53) ++local_dns;
    return 42;
}
static void packet(uint8_t *b,bool ethernet,uint8_t proto,uint32_t src,uint32_t dest,uint16_t port) {
    memset(b,0,80); unsigned off=ethernet?14:0; if(ethernet){b[12]=8;b[13]=0;}
    b[off]=0x45; b[off+3]=40; b[off+8]=64; b[off+9]=proto;
    uint32_t v=swap32(src); memcpy(b+off+12,&v,4); v=swap32(dest); memcpy(b+off+16,&v,4);
    b[off+22]=port>>8; b[off+23]=port;
    if(proto==6)b[off+32]=0x50;
    else {b[off+24]=0;b[off+25]=20;}
}
'''
tests=r'''
static void activate(uint32_t binding) {
    tailnet_forward_mapping_t maps[TAILNET_FORWARD_MAX];
    s_runtime[0].resolved_ip=0x64400002;
    int count=tailnet_forward_snapshot_mappings(maps,TAILNET_FORWARD_MAX);
    tailnet_forward_prepare_install();
    for(int i=0;i<count;i++){maps[i].binding_ip_nbo=binding;tailnet_forward_mark_installed(&maps[i],true,NULL);}
}
int main(void) {
    struct netif sta={.name={'s','t'},.ip={swap32(0xc0000201)}};
    struct netif ap={.name={'a','p'},.ip={swap32(0xc0000301)},.napt=1};
    struct netif wg={.name={'w','g'},.ip={swap32(0x64400001)}};
    uint8_t bytes[80]; struct pbuf p={.payload=bytes,.len=54,.tot_len=54};
    s_count=1; s_rules[0]=(tailnet_forward_rule_t){.valid=1,.proto=6,.listen_port=2222,.destination_port=22,.source_network=0xc0000200,.source_prefix=24};
    /* Disabled at Wi-Fi receive time; enabling while queued must NOT let
     * an unauthorized source reach the new listener when the core runs. */
    packet(bytes,true,6,0xc6336402,0xc0000201,2222);
#if EARLY_FILTER
    assert(tailnet_forward_allow_uplink_packet(&p,sta.ip.addr));
#endif
    s_rules[0].enabled=1; activate(sta.ip.addr);
    p.payload=bytes+14; p.len=p.tot_len=40; core_depth=1;
    assert(__wrap_ip4_input(&p,&sta)==ERR_OK && freed==1 && !inputs && !translated);
    packet(bytes,false,6,0xc0000263,0xc0000201,2222); p.payload=bytes;
    assert(__wrap_ip4_input(&p,&sta)==42 && translated==1 && inputs==1);
    ppp_deny=1;{unsigned f=freed,in=inputs,tr=translated;assert(__wrap_ip4_input(&p,&sta)==ERR_OK&&freed==f+1&&inputs==in&&translated==tr);freed=f;}ppp_deny=0;
    /* A new saved policy cannot alter an old physical binding before the
     * TCP/IP installer replaces both the binding and its immutable policy. */
    tailnet_forward_mapping_t old=s_active[0].mapping;
    s_generation++;s_rules[0].source_network=0xc6336400;s_runtime[0].installed=false;
    assert(__wrap_ip4_input(&p,&sta)==42 && translated==2);
    tailnet_forward_mark_installed(&old,true,NULL);assert(!s_runtime[0].installed);
    activate(sta.ip.addr);assert(s_runtime[0].installed);
    assert(__wrap_ip4_input(&p,&sta)==ERR_OK && freed==2 && translated==2);
    packet(bytes,false,6,0xc6336463,0xc0000201,2222);
    assert(__wrap_ip4_input(&p,&sta)==42 && translated==3);
    freed=inputs=translated=0;
    packet(bytes,false,6,0xc0000263,0x64400001,2222);
    assert(__wrap_ip4_input(&p,&wg)==ERR_OK && freed==1 && !translated);
    /* AP-side DNS is not eligible for receive DNAT when AP NAPT is ON. */
    s_rules[0].proto=17; s_rules[0].listen_port=53;
    s_generation++;activate(sta.ip.addr);
    packet(bytes,false,17,0xc0000363,0xc0000301,53);
    assert(__wrap_ip4_input(&p,&ap)==42 && local_dns==1 && freed==1);
    ap.napt=0; assert(__wrap_ip4_input(&p,&ap)==ERR_OK && freed==2 && local_dns==1);
    /* Optional Ethernet uplink ("en") bound as the listener: same policy. */
    struct netif eth={.name={'e','n'},.ip={swap32(0xc0000401)}};
    s_rules[0]=(tailnet_forward_rule_t){.valid=1,.enabled=1,.proto=6,.listen_port=2222,.destination_port=22,.source_network=0xc0000400,.source_prefix=24};
    s_generation++;activate(eth.ip.addr);freed=translated=0;
    packet(bytes,false,6,0xc0000463,0xc0000401,2222);
    assert(__wrap_ip4_input(&p,&eth)==42 && translated==1);
    packet(bytes,false,6,0xc6336463,0xc0000401,2222);
    assert(__wrap_ip4_input(&p,&eth)==ERR_OK && freed==1 && translated==1); /* wrong source refused */
    /* The STA address is no longer the binding: its listener port is not ours. */
    packet(bytes,false,6,0xc0000463,0xc0000201,2222);
    assert(__wrap_ip4_input(&p,&sta)==ERR_OK && freed==2 && translated==1);
    core_depth=0; assert(!lock_depth);
    puts("PASS: actual IPv4 core wrapper rechecks queued packets against installed policy; denied packets freed without entering DNAT, accepted return preserved, WG denied, AP DNS preserved with NAPT ON, Ethernet uplink binding");
}
'''
with tempfile.TemporaryDirectory(prefix='tailnet-core-') as directory:
    path=Path(directory); (path/'lwip').mkdir()
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n',encoding='utf-8')
    (path/'lwip/pbuf.h').write_text('#pragma once\nstruct pbuf { struct pbuf *next; void *payload; unsigned short len,tot_len; };\n',encoding='utf-8')
    (path/'lwip/netif.h').write_text('#pragma once\nstruct netif { char name[2]; unsigned char napt; struct { unsigned addr; } ip; };\n',encoding='utf-8')
    (path/'test.c').write_text('#include "lwip/netif.h"\n'+fixture+conflicts+policy+functions+core+tests,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(path),'-I',str(ROOT/'main'),f'-DEARLY_FILTER={int(early_filter)}']
    if os.environ.get('TAILNET_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

# Host fixtures cannot prove that the production SDK actually enters the
# wrapper. Check both Ethernet and raw-IP callers in the exact linked ELF.
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--objdump')
parser.add_argument('--elf',type=Path)
args=parser.parse_args()
if args.elf:
    assert args.objdump, '--objdump is required with --elf'
    symbols=subprocess.check_output([args.objdump,'-t',str(args.elf)],text=True)
    def disassemble(name):
        raw=subprocess.check_output([args.objdump,'-d',f'--disassemble={name}',str(args.elf)],text=True)
        # Xtensa padding can desynchronize linear decoding in any caller,
        # including the policy wrapper. Re-enter only at real branch targets
        # within this exact symbol; never guess offsets or accept raw bytes.
        rows=[line.split() for line in symbols.splitlines() if line.split() and line.split()[-1]==name and ' F ' in line]
        if not rows:return raw
        row=rows[0];start=int(row[0],16);end=start+int(row[-2],16)
        targets=set(int(n,16) for n in re.findall(rf'\b(?:b[\w.]+|j(?:\.n)?)\s+[^\n]*\b([\da-f]+) <{re.escape(name)}\+0x[\da-f]+>',raw))
        for address in sorted(targets):
            assert start<=address<end
            raw+=subprocess.check_output([args.objdump,'-d',f'--start-address={address}',f'--stop-address={end}',str(args.elf)],text=True)
        return raw
    frames={}
    for name,limit in {'__wrap_ip4_input':128,'tailnet_forward_allow_ipv4_packet':128,
                       'prepare_dnat_packet':256,
                       'tailnet_reassemble':384,
                       'allow_packet':256,
                       'tailnet_forward_snapshot_mappings':384,'portmap_install_cb':2560}.items():
        match=re.search(rf'<{name}>:\s*\n[^\n]*\bentry\s+a1,\s*(0x[\da-f]+|\d+)',disassemble(name))
        assert match, f'Missing stack frame: {name}'
        frame=int(match[1],0); assert frame<=limit, f'{name} exceeds frame budget: {frame}'
        frames[name]=frame
    packet_symbols=[line.split()[-1] for line in symbols.splitlines() if ' F ' in line and line.split()[-1].startswith('packet_fields')]
    if packet_symbols:
        for name in packet_symbols:
            match=re.search(rf'<{re.escape(name)}>:\s*\n[^\n]*\bentry\s+a1,\s*(0x[\da-f]+|\d+)',disassemble(name))
            assert match, f'Missing parser frame: {name}'
            frames[name]=int(match[1],0); assert frames[name]<=256
    else:
        assert '<pbuf_copy_partial>' in disassemble('allow_packet'), 'Inlined parser must still perform bounded packet reads'
        frames['packet_fields']='inlined in budgeted allow_packet'
    assert '<tailnet_forward_allow_ipv4_packet>' in disassemble('__wrap_ip4_input')
    assert '<prepare_dnat_packet>' in disassemble('__wrap_ip4_input')
    assert '<tailnet_reassemble>' in disassemble('prepare_dnat_packet')
    assert '<ip4_input>' in disassemble('__wrap_ip4_input')
    assert '<__wrap_ip4_input>' in disassemble('ethernet_input')
    raw=disassemble('ip_input')
    assert '<__wrap_ip4_input>' in raw, 'Raw-IP input must enter the linked policy wrapper'
    print('PASS: exact ELF Ethernet/raw IPv4 calls enter policy wrapper before SDK input; stack frame budgets:',frames)
