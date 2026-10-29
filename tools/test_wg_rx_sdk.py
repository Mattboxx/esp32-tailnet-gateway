"""Actual RX adoption C with the pinned SDK's real pbuf lifecycle (host only).

LWIP_SOURCE selects reviewed ESP-IDF 5.5.3 lwIP. No VPN/crypto/hardware claims.
WG_RX_SANITIZE=1 enables Linux ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(os.environ.get('LWIP_SOURCE', str(Path.home()/'.platformio/packages/framework-espidf@3.50503.0/components/lwip/lwip')))
source = (ROOT/'external/microlink/components/microlink/src/ml_wg_mgr.c').read_text(encoding='utf-8')
start = source.index('typedef struct {\n    struct pbuf_custom pc;')
types = source[start:source.index('} ml_spiram_pbuf_t;', start)+len('} ml_spiram_pbuf_t;')]


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start)+2]+'\n'


actual = types+'\n'+function('static void ml_spiram_pbuf_free_fn(')+function('static struct pbuf *ml_owned_rx_pbuf_new(')
options = '''
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
#define LWIP_TCP 0
#define LWIP_UDP 0
#define LWIP_ICMP 0
#define LWIP_IGMP 0
#define LWIP_RAW 0
#define LWIP_DHCP 0
#define LWIP_AUTOIP 0
#define LWIP_NETIF_LOOPBACK 0
#define LWIP_STATS 0
#define LWIP_SUPPORT_CUSTOM_PBUF 1
#define IP_REASSEMBLY 0
#define IP_FRAG 0
'''
arch = '''
#include <stdio.h>
#include <stdlib.h>
#define BYTE_ORDER LITTLE_ENDIAN
#define LWIP_PLATFORM_DIAG(x) do { printf x; } while(0)
#define LWIP_PLATFORM_ASSERT(x) do { fprintf(stderr,"%s\\n",x);abort(); } while(0)
#define PACK_STRUCT_STRUCT __attribute__((packed))
#define LWIP_RAND() ((unsigned)1234567)
'''
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lwip/pbuf.h"
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
static void *payload_live,*wrapper_live;
static unsigned frees;static bool oom;
static void *heap_caps_malloc(size_t n,unsigned caps){
 assert(caps==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 if(oom)return NULL;assert(!wrapper_live);return wrapper_live=malloc(n);
}
static void heap_caps_free(void *p){
 assert(p&&(p==wrapper_live||p==payload_live));
 if(p==wrapper_live)wrapper_live=NULL;else payload_live=NULL;
 free(p);frees++;
}
'''
tests = r'''
int main(void){
 for(unsigned length=1;length<65536;length+=137){
  uint8_t *data=payload_live=malloc(length);assert(data);memset(data,0x42,length);
  unsigned before=frees;struct pbuf *p=ml_owned_rx_pbuf_new(data,length);assert(p);
  assert(p->payload==data&&p->len==length&&p->tot_len==length&&p->ref==1);
  assert(p->flags&PBUF_FLAG_IS_CUSTOM);assert(!p->next);
  pbuf_ref(p);assert(pbuf_free(p)==0);assert(frees==before);
  assert(((uint8_t*)p->payload)[length-1]==0x42);
  if(length>16){assert(pbuf_remove_header(p,16)==0);assert(p->payload==data+16);}
  assert(pbuf_free(p)==1);assert(!payload_live&&!wrapper_live&&frees==before+2);
 }
 uint8_t *data=payload_live=malloc(32);oom=true;
 assert(!ml_owned_rx_pbuf_new(data,32));assert(payload_live==data);
 heap_caps_free(data);oom=false;
 data=payload_live=malloc(32);assert(!ml_owned_rx_pbuf_new(data,65536));assert(payload_live==data);heap_caps_free(data);
 assert(!ml_owned_rx_pbuf_new(NULL,32));
 puts("PASS: actual RX adoption + real SDK pbuf custom flags, 479 sizes, retained refs, header adjustment, exact final free, allocation failure and oversize refusal (host SDK fixture)");
}
'''

with tempfile.TemporaryDirectory(prefix='wg-rx-sdk-') as directory:
    path = Path(directory); (path/'arch').mkdir()
    (path/'lwipopts.h').write_text(options, encoding='utf-8')
    (path/'arch/cc.h').write_text(arch, encoding='utf-8')
    c = path/'test.c'; c.write_text(fixture+actual+tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Wno-misleading-indentation', '-ffunction-sections',
             '-fdata-sections', '-Wl,--gc-sections', '-I', str(path), '-I', str(SDK/'src/include')]
    if os.environ.get('WG_RX_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path/('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'), *flags, str(c),
        *(str(SDK/'src/core'/f) for f in ('pbuf.c','mem.c','memp.c','def.c')), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
