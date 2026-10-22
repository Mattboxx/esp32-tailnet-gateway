"""Actual bounded tunnel reassembly + policy C; synthetic pbuf/map/time.
No actual WireGuard encryption, FreeRTOS scheduling or two-real-client test.
"""
import ast
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ML=ROOT/'external/microlink/components/microlink'
tree=ast.parse((ROOT/'tools/test_tailnet_authorization.py').read_text(encoding='utf-8'))
def constant(name):
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
SUPPORT=r'''
#define PBUF_RAW 0
#define PBUF_RAM 0
static unsigned allocated,freed,pool_fail,pbuf_fail;
static struct pbuf *pbuf_alloc(int layer,uint16_t size,int type){
    (void)layer;(void)type;if(pbuf_fail)return NULL;
    struct pbuf *p=calloc(1,sizeof *p);assert(p);p->payload=calloc(1,size);assert(p->payload);
    p->len=p->tot_len=size;allocated++;return p;
}
static void pbuf_free(struct pbuf *p){if(p){free(p->payload);free(p);freed++;}}
void *reassembly_test_alloc(size_t n){return pool_fail?NULL:malloc(n);}
#define ML_REASSEMBLY_HOST_TEST 1
#include "ml_reassembly.c"
static struct pbuf *fragment(unsigned family,unsigned proto,unsigned port,unsigned offset,unsigned n,bool more,unsigned id){
    unsigned h=family==4?20:48;
    struct pbuf *p=pbuf_alloc(0,(uint16_t)(h+n),0);uint8_t *b=p->payload;
    struct pbuf original=packet(family,proto,family==4?"100.64.0.1":"fd7a:115c:a1e0::1",
                               family==4?"100.64.0.10":"fd7a:115c:a1e0::10",40000,port,2,0);
    memcpy(b,original.payload,family==4?20:40);
    uint8_t data[32]={0};memcpy(data,(uint8_t*)original.payload+(family==4?20:40),proto==6?20:8);
    if(proto==17){data[4]=0;data[5]=32;}
    if(offset<32){unsigned copy=n<32-offset?n:32-offset;memcpy(b+h,data+offset,copy);}
    if(family==4){b[2]=(h+n)>>8;b[3]=h+n;b[4]=id>>8;b[5]=id;
        unsigned f=offset/8|(more?0x2000:0);b[6]=f>>8;b[7]=f;b[10]=b[11]=0;
        uint16_t c=rchecksum(b,20);b[10]=c>>8;b[11]=c;
    }else{b[4]=(n+8)>>8;b[5]=n+8;b[6]=44;b[40]=proto;
        unsigned f=offset|(more?1:0);b[42]=f>>8;b[43]=f;b[44]=id>>24;b[45]=id>>16;b[46]=id>>8;b[47]=id;}
    return p;
}
static bool feed(unsigned family,unsigned proto,unsigned port,unsigned offset,unsigned n,bool more,unsigned id,const uint8_t *key){
    struct pbuf *p=ml_reassemble_rx(fragment(family,proto,port,offset,n,more,id),key);
    if(!p)return false;
    bool allow=ml_policy_rx(p,key);pbuf_free(p);return allow;
}
static struct pbuf *tx_fragment(unsigned family,unsigned proto,unsigned offset,bool more,unsigned id){
    struct pbuf *p=fragment(family,proto,22,offset,16,more,id);uint8_t *b=p->payload,temp[16];
    unsigned n=family==4?4:16,src=family==4?12:8,dst=family==4?16:24;
    memcpy(temp,b+src,n);memcpy(b+src,b+dst,n);memcpy(b+dst,temp,n);
    if(family==4){b[10]=b[11]=0;uint16_t c=rchecksum(b,20);b[10]=c>>8;b[11]=c;}
    return p;
}
static struct pbuf *prepend6(struct pbuf *p,unsigned kind){
    struct pbuf *extended=pbuf_alloc(0,p->tot_len+8,0);uint8_t *b=extended->payload,*old=p->payload;
    memcpy(b,old,40);memset(b+40,0,8);memcpy(b+48,old+40,p->tot_len-40);
    b[6]=(uint8_t)kind;b[40]=old[6];unsigned n=r16(b+4)+8;b[4]=n>>8;b[5]=n;pbuf_free(p);return extended;
}
static bool reply(unsigned family,unsigned proto){
    return rx(family,proto,family==4?"100.64.0.1":"fd7a:115c:a1e0::1",family==4?"100.64.0.10":"fd7a:115c:a1e0::10",22,40000,0x12,key_a);
}
static void tx_cases(void){
    for(unsigned family=4;family<=6;family+=2)for(unsigned proto=6;proto<=17;proto+=11){
        standard();ml_reassembly_clear();
        struct pbuf *first=tx_fragment(family,proto,0,true,90),*last=tx_fragment(family,proto,16,false,90);
        assert(ml_fragment_tx_check(first,key_a)==1&&ml_fragment_tx_check(last,key_a)==1);
        assert(ml_fragment_tx_check(first,key_b)==-1);
        ml_fragment_tx_result(first,key_a,true);assert(!reply(family,proto));
        ml_fragment_tx_result(last,key_a,true);assert(reply(family,proto));pbuf_free(first);pbuf_free(last);
        standard();ml_reassembly_clear();first=tx_fragment(family,proto,0,true,91);last=tx_fragment(family,proto,16,false,91);
        ml_fragment_tx_result(first,key_a,true);ml_fragment_tx_result(last,key_a,false);
        ml_fragment_tx_result(last,key_a,true);assert(!reply(family,proto));pbuf_free(first);pbuf_free(last);
        standard();ml_reassembly_clear();first=tx_fragment(family,proto,0,true,92);last=tx_fragment(family,proto,16,false,92);
        ml_fragment_tx_result(first,key_a,true);assert(apply("{\"PeersRemoved\":[2]}"));ml_fragment_tx_result(last,key_a,true);
        assert(!reply(family,proto));pbuf_free(first);pbuf_free(last);
    }
    assert(apply(ALL));ml_reassembly_clear();
    struct pbuf *first=prepend6(prepend6(fragment(6,6,80,0,16,true,93),60),0);
    struct pbuf *last=prepend6(prepend6(fragment(6,6,80,16,16,false,93),60),0);
    assert(!ml_reassemble_rx(last,key_a));struct pbuf *complete=ml_reassemble_rx(first,key_a);
    assert(complete&&ml_policy_rx(complete,key_a));pbuf_free(complete);
    first=prepend6(fragment(6,6,80,0,16,true,94),0);((uint8_t*)first->payload)[42]=0x80;
    assert(!ml_reassemble_rx(first,key_a));
    first=fragment(6,6,80,0,16,true,95);for(unsigned i=0;i<4;i++)first=prepend6(first,i==3?0:60);
    assert(!ml_reassemble_rx(first,key_a));
}
int main(void){
    standard();pool_fail=1;assert(!feed(4,6,80,0,16,true,1,key_a));pool_fail=0;
    for(unsigned family=4;family<=6;family+=2)for(unsigned proto=6;proto<=17;proto+=11){
        assert(apply(ALL));ml_reassembly_clear();
        assert(!feed(family,proto,80,16,16,false,1,key_a));
        assert(feed(family,proto,80,0,16,true,1,key_a)); /* Out of order. */
        ml_reassembly_clear();standard();
        assert(!feed(family,proto,22,0,16,true,2,key_a));
        assert(!feed(family,proto,22,16,16,false,2,key_a)); /* Reassembly is not permission. */
        assert(apply(ALL));ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,3,key_b)); /* Visible wrong key/source. */
        assert(!feed(family,proto,80,16,16,false,3,key_a));
        assert(!feed(family,proto,80,0,16,true,3,key_b));
        assert(feed(family,proto,80,0,16,true,3,key_a));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,4,key_a));
        assert(!feed(family,proto,80,0,16,true,4,key_a)); /* Duplicate destroys context. */
        assert(!feed(family,proto,80,16,16,false,4,key_a));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,5,key_a));
        assert(!feed(family,proto,80,8,16,true,5,key_a)); /* Overlap. */
        assert(!feed(family,proto,80,16,16,false,5,key_a));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,6,key_a));clock_ms+=RAGE;
        assert(!feed(family,proto,80,16,16,false,6,key_a));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,7,key_a));
        assert(apply("{\"PacketFilter\":[]}"));assert(apply(ALL));
        assert(!feed(family,proto,80,16,16,false,7,key_a)); /* No cross-epoch mixture. */
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,8,key_a));
        assert(apply("{\"PeersRemoved\":[1]}"));
        assert(!feed(family,proto,80,16,16,false,8,key_a));assert(apply(ALL));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,15,true,9,key_a)); /* Alignment. */
        assert(!feed(family,proto,80,16,16,false,9,key_a));
        ml_reassembly_clear();
        assert(!feed(family,proto,80,0,16,true,10,key_a));
        pbuf_fail=1; /* Create final input before simulating output allocation OOM. */
        pbuf_fail=0;struct pbuf *last=fragment(family,proto,80,16,16,false,10);
        pbuf_fail=1;assert(!ml_reassemble_rx(last,key_a));pbuf_fail=0;
        assert(!feed(family,proto,80,16,16,false,10,key_a));
    }
    assert(apply(ALL));ml_reassembly_clear();
    assert(!feed(4,6,80,0,16,true,11,key_a));assert(!feed(4,6,80,0,16,true,12,key_a));
    assert(!feed(4,6,80,0,16,true,13,key_a)); /* No eviction of live contexts. */
    assert(feed(4,6,80,16,16,false,11,key_a));assert(feed(4,6,80,16,16,false,12,key_a));
    assert(!feed(4,6,80,16,16,false,13,key_a));ml_reassembly_clear();
    assert(!feed(4,6,80,4080,16,false,14,key_a)); /* Output size cap. */
    struct pbuf *bad=fragment(4,6,80,0,16,true,15);((uint8_t*)bad->payload)[10]^=1;
    assert(!ml_reassemble_rx(bad,key_a));assert(!feed(4,6,80,16,16,false,15,key_a));
    ml_reassembly_clear();rbusy=1;assert(!feed(6,6,80,0,16,true,16,key_a));rbusy=0;
    assert(!feed(6,6,80,16,16,false,16,key_a));
    ml_reassembly_clear();clock_ms=UINT32_MAX-100;
    assert(!feed(4,6,80,0,16,true,17,key_a));clock_ms=100;
    assert(feed(4,6,80,16,16,false,17,key_a));
    tx_cases();ml_policy_reset();for(unsigned d=0;d<2;d++){free(rpools[d]);rpools[d]=NULL;}assert(allocated==freed);
    printf("PASS: bounded IPv4/IPv6 TCP/UDP reassembly, current key/epoch + final policy, overlap/expiry/capacity/OOM and balanced pbuf ownership; pool=%zu bytes (host only)\n",RSLOTS*sizeof(reassembly_slot));
}
'''
WG_TEST=r'''
#undef ml_policy_rx
#undef ml_reassemble_rx
#define PBUF_RAW 0
#define ML_REASSEMBLY_HOST_TEST 1
void *reassembly_test_alloc(size_t n){return malloc(n);}
#include "ml_reassembly.c"
'''+ 'static struct pbuf *fragment'+SUPPORT.split('static struct pbuf *fragment',1)[1].split('static bool feed',1)[0]
WG_MAIN=r'''
#define ml_policy_rx rx_hook
#define ml_reassemble_rx reassembly_hook
'''
WG_BODY=r'''
#undef ml_policy_rx
#undef ml_reassemble_rx
int main(void){
    (void)key_b;
    struct netif n={.input=deliver};struct wireguard_device d={.netif=&n};
    struct wireguard_peer peer={.kp={.receiving_valid=true}};memcpy(peer.public_key,key_a,32);
    peer.allowed_source_ips[0]=(struct wireguard_allowed_ip){.valid=true,.ip={.addr=htonl(0x64400001),.type=4},.mask={.addr=0xffffffff,.type=4}};
    ip_addr_t outer={0};reassembly_hook=ml_reassemble_rx;
    for(unsigned family=4;family<=6;family+=2)for(unsigned proto=6;proto<=17;proto+=11)for(unsigned denied=0;denied<3;denied++){
        ml_reassembly_clear();assert(apply(ALL));deliveries=translations=0;crypto_ok=denied!=2;
        if(denied==1)assert(apply("{\"PacketFilter\":[]}"));
        for(unsigned part=0;part<2;part++){
            struct pbuf *p=fragment(family,proto,80,part*16,16,!part,99);
            struct message_transport_data hdr={0};memcpy(hdr.enc_packet,p->payload,p->tot_len);
            unsigned len=p->tot_len;pbuf_free(p);
            wireguardif_process_data_message(&d,&peer,&hdr,len+16,&outer,1234);
            assert(deliveries+translations==(unsigned)(part==1&&!denied));assert(allocs==frees);
        }
    }
    ml_policy_reset();for(unsigned d=0;d<2;d++){free(rpools[d]);rpools[d]=NULL;}
    puts("PASS: actual WG RX + actual reassembly/policy, IPv4/IPv6 TCP/UDP allow/deny/crypto-failure before translation, balanced pbufs (mock crypto/netif)");
}
'''
with tempfile.TemporaryDirectory(prefix='policy-reassembly-') as directory:
    path=Path(directory);(path/'lwip').mkdir();(path/'lwip/pbuf.h').write_text(constant('PBUF'))
    (path/'test.c').write_text('#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n'+constant('HEAD')+SUPPORT)
    flags=['-std=c11','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-function','-O1','-g','-I',str(path),'-I',str(ML/'include'),'-I',str(ML/'src')]
    libs=['-lws2_32'] if os.name=='nt' else ['-lm']
    source=os.environ.get('CJSON_SOURCE')
    if source:flags+=['-I',str(Path(source).parent),source]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('POLICY_SANITIZE')=='1':
        flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if os.environ.get('POLICY_NO_PIE')=='1' and os.name!='nt':flags+=['-fno-pie','-no-pie']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=45)
    wg_source=(ML/'components/wireguard_lwip/src/wireguardif.c').read_text(encoding='utf-8')
    receive='static void wireguardif_process_data_message'+wg_source.split('static void wireguardif_process_data_message',1)[1].split('\nstatic struct pbuf *wireguardif_initiate_handshake',1)[0]
    (path/'test.c').write_text('#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n'+constant('HEAD')+constant('WG_FIXTURE')+WG_TEST+WG_MAIN+receive+WG_BODY)
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=45)
