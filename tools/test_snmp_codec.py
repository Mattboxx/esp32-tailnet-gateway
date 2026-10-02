"""Compile and exercise the real SNMP codec/PDU functions with synthetic MIBs.

No device access. Set SNMP_SANITIZE=1 on Linux to add ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "components/snmp_agent/snmp_agent.c").read_text(encoding="utf-8")

def section(start, end):
    return source.split(start, 1)[1].split(end, 1)[0]

constants = section('#define PKT_BUF', '/* ------------------------------------------------------------------ */')
constants = '#define PKT_BUF' + constants
buffers = section('typedef struct {\n    uint8_t rx[PKT_BUF];', '} snmp_buffers_t;')
buffers = 'typedef struct {\n    uint8_t rx[PKT_BUF];' + buffers + '} snmp_buffers_t;\n'
codec = 'static int ber_put_len' + section('static int ber_put_len', '/* OID table')
parser = 'static int process_pdu' + section('static int process_pdu', '/* SNMP task')

fixture = r'''
typedef struct { uint32_t arc[MAX_OID]; int n; } oid_t;
static const struct { oid_t oid; } s_mib[] = {{{{1,3,6,1,2,1,1,1,0},9}}};
static int mib_get(const uint32_t *arc, int n) {
    return n == 9 && !memcmp(arc, s_mib[0].oid.arc, 9*sizeof(*arc)) ? 0 : -1;
}
static int mib_getnext(const uint32_t *arc, int n) {
    for(int i=0;i<n && i<9;i++) {
        if(arc[i] < s_mib[0].oid.arc[i]) return 0;
        if(arc[i] > s_mib[0].oid.arc[i]) return -1;
    }
    return n < 9 ? 0 : -1;
}
static int encode_val(uint8_t *b, int cap, int row) {
    (void)row; char str[256]; memset(str,'x',255); str[255]=0;
    return ber_enc_str(b,cap,str);
}
'''
tests = r'''
static int wrap(uint8_t *out, uint8_t tag, const uint8_t *in, int n) {
    uint8_t header[4]; int h=seq_hdr(header,4,tag,n);
    memcpy(out,header,h); memcpy(out+h,in,n); return h+n;
}
static int make_request(uint8_t *out, int version, int tag, const char *comm, int ridlen) {
    uint8_t oid[128], vb[160], vbl[180], pdu[300], body[600], message[700];
    int a=ber_enc_oid(oid,sizeof oid,s_mib[0].oid.arc,9);
    oid[a++]=5; oid[a++]=0;
    a=wrap(vb,0x30,oid,a); a=wrap(vbl,0x30,vb,a);
    int p=0; pdu[p++]=2; pdu[p++]=ridlen;
    for(int i=0;i<ridlen;i++) pdu[p++]=1;
    for(int i=0;i<2;i++) {pdu[p++]=2;pdu[p++]=1;pdu[p++]=0;}
    memcpy(pdu+p,vbl,a);p+=a;
    p=wrap(message,tag,pdu,p);
    int b=0;body[b++]=2;body[b++]=1;body[b++]=version;
    b+=ber_enc_str(body+b,sizeof body-b,comm);
    memcpy(body+b,message,p);b+=p;
    return wrap(out,0x30,body,b);
}
int main(void) {
    snmp_buffers_t *buffers=calloc(1,sizeof(*buffers)); assert(buffers);
    uint8_t in[PKT_BUF], out[PKT_BUF+16];
    int n=make_request(in,1,0xa0,"fixture",1);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)>255);
    assert(process_pdu(in,n,out,16,"fixture",buffers)<0);
    assert(process_pdu(in,n,out,PKT_BUF,"wrong",buffers)<0);
    for(int i=0;i<n;i++) assert(process_pdu(in,i,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,0,0xa1,"fixture",4);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)>0);
    n=make_request(in,3,0xa0,"fixture",1);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa3,"fixture",1); /* SET must never be answered */
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa0,"fixture",0);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    n=make_request(in,1,0xa0,"fixture",8);
    assert(process_pdu(in,n,out,PKT_BUF,"fixture",buffers)<0);
    uint32_t arc[MAX_OID]; int count;
    const uint8_t bad_oid[]={43,0xff,0xff,0xff,0xff,0xff,0x7f};
    assert(!ber_dec_oid(bad_oid,sizeof bad_oid,arc,&count,MAX_OID));
    uint32_t rng=1234567;
    for(int iteration=0;iteration<50000;iteration++) {
        n=make_request(in,1,0xa0,"fixture",1);
        if(iteration%2) {
            rng=rng*1664525u+1013904223u; n=rng%PKT_BUF;
            for(int i=0;i<n;i++) {rng=rng*1664525u+1013904223u;in[i]=rng>>24;}
        } else {
            rng=rng*1664525u+1013904223u; int at=rng%n;
            rng=rng*1664525u+1013904223u; in[at]=rng>>24;
        }
        memset(out,0xa5,sizeof out);
        int reply=process_pdu(in,n,out,PKT_BUF,"fixture",buffers);
        assert(reply<=PKT_BUF);
        for(int i=PKT_BUF;i<(int)sizeof out;i++) assert(out[i]==0xa5);
    }
    free(buffers);puts("PASS: SNMP v1/v2c, wrong community, SET rejection, truncation, lengths, OID overflow, 50000 malformed/mutated packets");
}
'''
program = '#define _POSIX_C_SOURCE 200809L\n#include <stdint.h>\n#include <stdbool.h>\n#include <string.h>\n#include <stdlib.h>\n#include <stdio.h>\n#include <assert.h>\n' + constants + buffers + codec + fixture + parser + tests
with tempfile.TemporaryDirectory(prefix="snmp-codec-") as directory:
    path = Path(directory)
    (path / "test.c").write_text(program, encoding="utf-8")
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get("SNMP_SANITIZE") == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path/'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
