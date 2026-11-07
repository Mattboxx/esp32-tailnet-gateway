"""Execute actual MicroLink RX adoption/dispatch C with allocator/pbuf fixtures.

Host ownership/failure tests, NOT real crypto, SDK pbuf or ESP qualification.
WG_RX_SANITIZE=1 enables Linux ASan/UBSan. No network or physical device access.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'external/microlink/components/microlink/src/ml_wg_mgr.c'
source = SOURCE.read_text(encoding='utf-8')


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start)+2]+'\n'


types = source[source.index('typedef struct {\n    struct pbuf_custom pc;'):]
types = types[:types.index('} ml_spiram_pbuf_t;')+len('} ml_spiram_pbuf_t;')]
actual = types+'\n'+function('static void ml_spiram_pbuf_free_fn(')+function(
    'static struct pbuf *ml_owned_rx_pbuf_new(')+function('static void process_wg_packet(')

HEADER = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint16_t u16_t;
#define ESP_LOGD(...) ((void)0)
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
#define PBUF_RAW 0
#define PBUF_REF 1
#define IPADDR_TYPE_V4 4
struct pbuf {void *payload;uint16_t len,tot_len,ref;};
struct pbuf_custom {struct pbuf pbuf;void (*custom_free_function)(struct pbuf *);};
struct ip4_addr {uint32_t addr;};
typedef struct {int type;struct ip4_addr ip4;} ip_addr_t;
#define IP_SET_TYPE_VAL(a,t) ((a).type=(t))
#define ip_2_ip4(a) (&(a)->ip4)
static void ip4_addr_set_u32(struct ip4_addr *a,uint32_t v){a->addr=v;}
static void ip_addr_set_any(bool v6,ip_addr_t *a){assert(!v6);a->type=4;a->ip4.addr=0;}
static uint32_t htonl(uint32_t v){return ((v&255)<<24)|((v&65280)<<8)|((v>>8)&65280)|(v>>24);}
struct netif {void *state;};
typedef struct {struct netif *wg_netif;} microlink_t;
typedef struct {uint8_t *data;size_t len;bool via_derp;uint32_t src_ip;uint16_t src_port;uint8_t src_pubkey[32];} ml_rx_packet_t;
static void *live[4];static size_t live_size[4];
static bool fail_wrapper,fail_custom,hold;static int frees,wrapper_calls,consumer_calls;
static uint8_t *expected_payload;static uint32_t expected_ip;static struct pbuf *held;
static void *allocate(size_t n){
 void *p=malloc(n);assert(p);for(int i=0;i<4;i++)if(!live[i]){live[i]=p;live_size[i]=n;return p;}abort();
}
static void fake_free(void *p){
 if(!p)return;
 for(int i=0;i<4;i++)if(live[i]==p){memset(p,0xdd,live_size[i]);free(p);live[i]=NULL;frees++;return;}
 assert(!"double free or unknown allocation");
}
static void *heap_caps_malloc(size_t n,unsigned caps){
 assert(caps==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));wrapper_calls++;return fail_wrapper?NULL:allocate(n);
}
static void heap_caps_free(void *p){fake_free(p);}
static struct pbuf *pbuf_alloced_custom(int layer,u16_t len,int type,
 struct pbuf_custom *pc,void *data,u16_t capacity){
 assert(layer==PBUF_RAW&&type==PBUF_REF&&len==capacity&&len>0);
 if(fail_custom)return NULL;
 pc->pbuf=(struct pbuf){.payload=data,.len=len,.tot_len=len,.ref=1};return &pc->pbuf;
}
static void pbuf_ref(struct pbuf *p){assert(p->ref);p->ref++;}
static void pbuf_free(struct pbuf *p){assert(p->ref);if(!--p->ref)((struct pbuf_custom*)p)->custom_free_function(p);}
static void wireguardif_network_rx(void *device,void *pcb,struct pbuf *p,const ip_addr_t *addr,uint16_t port){
 assert(device==(void*)1&&!pcb&&p->payload==expected_payload&&port==12345);
 assert(addr->type==4&&addr->ip4.addr==expected_ip&&p->len==p->tot_len);
 assert(((uint8_t*)p->payload)[0]==0x42);((uint8_t*)p->payload)[0]=0x24;consumer_calls++;
 if(hold){pbuf_ref(p);held=p;}pbuf_free(p);
}
#define free fake_free
'''

TESTS = r'''
#undef free
static void clean(void){for(int i=0;i<4;i++)assert(!live[i]);}
static void reset(void){clean();frees=wrapper_calls=consumer_calls=0;fail_wrapper=fail_custom=hold=false;held=NULL;}
static ml_rx_packet_t packet(size_t len,bool relay){
 uint8_t *p=allocate(len?len:1);memset(p,0x42,len?len:1);expected_payload=p;
 expected_ip=relay?0:htonl(0x11223344);
 return (ml_rx_packet_t){.data=p,.len=len,.via_derp=relay,.src_ip=0x11223344,.src_port=12345};
}
int main(void){
 struct netif netif={.state=(void*)1};microlink_t ml={.wg_netif=&netif};
 for(int relay=0;relay<2;relay++)for(int delayed=0;delayed<2;delayed++){
  const size_t lengths[]={4,32,1280,1420,2048,65535};
  for(unsigned i=0;i<sizeof lengths/sizeof lengths[0];i++){
   reset();hold=delayed;ml_rx_packet_t pkt=packet(lengths[i],relay);process_wg_packet(&ml,&pkt);
   assert(consumer_calls==1&&wrapper_calls==1);
   if(delayed){assert(frees==0&&held&&held->ref==1);assert(((uint8_t*)held->payload)[0]==0x24);pbuf_free(held);}
   assert(frees==2);clean();
  }
 }
 for(int mode=0;mode<6;mode++){
  reset();ml_rx_packet_t pkt=packet(mode==3?0:32,false);
  if(mode==0)fail_wrapper=true;
  if(mode==1)fail_custom=true;
  if(mode==2)ml.wg_netif=NULL;
  if(mode==4)netif.state=NULL;
  if(mode==5)pkt.len=65536; /* invalid size: must not truncate into u16_t */
  process_wg_packet(&ml,&pkt);assert(!consumer_calls);assert(frees==(mode==1?2:1));clean();
  ml.wg_netif=&netif;netif.state=(void*)1;
 }
 reset();ml_rx_packet_t none={.data=NULL,.len=32};process_wg_packet(&ml,&none);assert(!consumer_calls);clean();
 for(int i=0;i<4000;i++){
  reset();fail_wrapper=i%7==0;fail_custom=i%11==0;hold=i%3==0;
  ml_rx_packet_t pkt=packet(32+(i%1400),i%2);process_wg_packet(&ml,&pkt);
  if(held)pbuf_free(held);clean();
 }
 puts("PASS: actual RX adoption/dispatch, direct/DERP address, retained ref lifetime, zero-copy identity, OOM, invalid lengths, teardown and 4000 ownership cycles (host fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='wg-rx-owned-') as directory:
    path = Path(directory)
    c = path/'test.c'; c.write_text(HEADER+actual+TESTS, encoding='utf-8')
    binary = path/('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation']
    if os.environ.get('WG_RX_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'), *flags, str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
