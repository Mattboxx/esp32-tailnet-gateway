"""Actual policy C: related ICMP and bounded IPv6 headers. No real tunnel."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'tools/test_tailnet_authorization.py').read_text(encoding='utf-8'))
def constant(name):
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))

BODY=r'''
static struct pbuf error_packet(unsigned family,unsigned protocol,unsigned type,unsigned code,unsigned quoted_port){
    static uint8_t bytes[160];
    const char *local=family==4?"100.64.0.10":"fd7a:115c:a1e0::10";
    const char *remote=family==4?"100.64.0.1":"fd7a:115c:a1e0::1";
    struct pbuf original=packet(family,protocol,local,remote,40000,quoted_port,2,0);
    uint8_t quote[80];unsigned n=family==4?28:48;memcpy(quote,original.payload,n);
    struct pbuf outer=packet(family,family==4?1:58,remote,local,0,0,type,0);
    unsigned h=family==4?20:40;memset(bytes,0,sizeof bytes);memcpy(bytes,outer.payload,h+8);
    bytes[h+1]=code;memcpy(bytes+h+8,quote,n);
    unsigned total=h+8+n;
    if(family==4){bytes[2]=total>>8;bytes[3]=total;}else{bytes[4]=(total-40)>>8;bytes[5]=total-40;}
    return (struct pbuf){.payload=bytes,.len=total,.tot_len=total};
}
int main(void){
    /* A transport outage blocks immediately, but an identical COMPLETE map
     * within 30 s can retain return state. A delta, revoke or longer outage
     * cannot inherit that state. This is not permission to run offline. */
    standard();
    struct pbuf out=packet(4,6,"100.64.0.10","100.64.0.1",50000,22,2,0);ml_policy_sent(&out,key_a);
    assert(rx(4,6,"100.64.0.1","100.64.0.10",22,50000,0x12,key_a));
    ml_policy_suspend();assert(ml_policy_peer_status(key_a)==-1);
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",22,50000,0x12,key_a));
    out=packet(4,6,"100.64.0.10","100.64.0.1",50000,22,2,0);assert(!ml_policy_tx(&out,key_a));
    assert(apply("{\"KeepAlive\":true}"));assert(!rx(4,6,"100.64.0.1","100.64.0.10",40000,80,2,key_a));
    clock_ms+=100;assert(apply(FULL));assert(rx(4,6,"100.64.0.1","100.64.0.10",22,50000,0x12,key_a));
    ml_policy_suspend();assert(!apply("{\"PacketFilter\":[]}"));assert(apply(FULL));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",22,50000,0x12,key_a));
    out=packet(4,6,"100.64.0.10","100.64.0.1",50000,22,2,0);ml_policy_sent(&out,key_a);
    ml_policy_suspend();clock_ms+=RESUME_WINDOW_MS;assert(apply(FULL));
    assert(!rx(4,6,"100.64.0.1","100.64.0.10",22,50000,0x12,key_a));
    ml_policy_status_t status;ml_policy_reset();ml_policy_get_status(&status);assert(!status.authority_ready);
    assert(apply(ALL));ml_policy_get_status(&status);assert(status.authority_ready && status.peers==2 && status.expanded_rules==1);
    for(unsigned family=4;family<=6;family+=2)for(unsigned proto=6;proto<=17;proto+=11){
        ml_policy_reset();assert(apply(ALL));
        struct pbuf err=error_packet(family,proto,family==4?3:2,family==4?4:0,443);
        assert(!ml_policy_rx(&err,key_a)); /* No successful outgoing flow. */
        struct pbuf request=packet(family,proto,family==4?"100.64.0.10":"fd7a:115c:a1e0::10",
                                  family==4?"100.64.0.1":"fd7a:115c:a1e0::1",40000,443,2,0);
        assert(ml_policy_tx(&request,key_a));ml_policy_sent(&request,key_a);
        err=error_packet(family,proto,family==4?3:2,family==4?4:0,443);
        assert(ml_policy_rx(&err,key_a));assert(!ml_policy_rx(&err,key_b));
        err=error_packet(family,proto,family==4?3:2,family==4?4:0,444);assert(!ml_policy_rx(&err,key_a));
        err=error_packet(family,proto,family==4?3:2,family==4?4:0,443);
        err.tot_len--;err.len--;assert(!ml_policy_rx(&err,key_a));
        err=error_packet(family,proto,family==4?3:2,family==4?4:0,443);
        assert(apply("{\"PeersRemoved\":[1]}"));assert(!ml_policy_rx(&err,key_a));
    }
    assert(apply(ALL));uint8_t extended[88];
    struct pbuf plain=packet(6,6,"fd7a:115c:a1e0::1","fd7a:115c:a1e0::10",40000,80,2,0);
    memcpy(extended,plain.payload,40);memset(extended+40,0,8);memcpy(extended+48,(uint8_t*)plain.payload+40,20);
    extended[6]=60;extended[40]=6;extended[5]=28;
    struct pbuf p={.payload=extended,.len=68,.tot_len=68};assert(ml_policy_rx(&p,key_a));
    extended[42]=0x80;assert(!ml_policy_rx(&p,key_a)); /* Unknown option. */
    extended[42]=0;extended[6]=44;assert(ml_policy_rx(&p,key_a)); /* Atomic. */
    extended[43]=1;assert(!ml_policy_rx(&p,key_a)); /* Fragment needs reassembly. */
    extended[43]=0;extended[6]=43;assert(!ml_policy_rx(&p,key_a)); /* Routing hdr. */
    /* Reply evidence: only an ADMITTED reply on a flow this node sent counts. */
    ml_policy_reset();standard();
    const uint8_t svc[4]={100,64,0,1},other[4]={100,64,0,2};uint32_t age=0;
    assert(!ml_policy_reply_age(17,svc,53,&age));
    struct pbuf q=packet(4,17,"100.64.0.10","100.64.0.1",40001,53,0,0);ml_policy_sent(&q,key_a);
    assert(!ml_policy_reply_age(17,svc,53,&age)); /* a send alone is not a reply */
    assert(!rx(4,17,"100.64.0.1","100.64.0.10",53,40001,0,key_b)); /* wrong key admits nothing */
    assert(!ml_policy_reply_age(17,svc,53,&age));
    clock_ms+=10;assert(rx(4,17,"100.64.0.1","100.64.0.10",53,40001,0,key_a));
    clock_ms+=1500;assert(ml_policy_reply_age(17,svc,53,&age)&&age==1500);
    assert(!ml_policy_reply_age(17,svc,54,&age)&&!ml_policy_reply_age(6,svc,53,&age)&&!ml_policy_reply_age(17,other,53,&age));
    assert(!ml_policy_reply_age(17,NULL,53,&age)&&!ml_policy_reply_age(17,svc,53,NULL));
    q=packet(4,17,"100.64.0.10","100.64.0.1",40001,53,0,0);ml_policy_sent(&q,key_a);
    assert(ml_policy_reply_age(17,svc,53,&age)&&age==1500); /* resend keeps the original reply time */
    clock_ms+=200;assert(ml_policy_reply_age(17,svc,53,&age)&&age==1700);
    ml_policy_suspend();assert(!ml_policy_reply_age(17,svc,53,&age)); /* no evidence while suspended */
    ml_policy_reset();assert(!ml_policy_reply_age(17,svc,53,&age));
    ml_policy_reset();puts("PASS: actual policy related TCP/UDP ICMPv4/v6, wrong key/tuple/truncation/revoke; bounded IPv6 options/atomic fragment; admitted-reply evidence (host only)");
}
'''
with tempfile.TemporaryDirectory(prefix='policy-protocol-') as directory:
    path=Path(directory);(path/'lwip').mkdir();(path/'lwip/pbuf.h').write_text(constant('PBUF'))
    (path/'test.c').write_text('#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n'+constant('HEAD')+BODY)
    ml=ROOT/'external/microlink/components/microlink'
    flags=['-std=c11','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-function','-O1','-g','-I',str(path),'-I',str(ml/'include'),'-I',str(ml/'src')]
    libs=['-lws2_32'] if os.name=='nt' else ['-lm']
    source=os.environ.get('CJSON_SOURCE')
    if source:flags+=['-I',str(Path(source).parent),source]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('POLICY_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run(['gcc',*flags,str(path/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
