"""Actual reference crypto C: RFC 8439 KATs and independent AEAD comparisons.

Host tests include an ESP32-S3 attribute fixture; ELF placement and real-device
timing/resources are separate gates. No network/device access. Test-only keys.
HOTLOOP_SANITIZE=1 enables Linux ASan/UBSan.
Vectors: https://www.rfc-editor.org/rfc/rfc8439 (2.5.2 and Appendix A.1).
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

ROOT = Path(__file__).resolve().parents[1]
WG = ROOT/'external/microlink/components/microlink/components/wireguard_lwip/src'


def array(name, data):
    return 'static const uint8_t '+name+'[]="'+''.join('\\x%02x' % b for b in data)+'";\n'


data = ''
rows = []
lengths = (0, 1, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 129, 255, 256, 1024, 1240, 1280, 1400, 1420, 1500)
for i, length in enumerate(lengths):
    key = hashlib.sha256(b'public-test-fixture-key'+bytes([i])).digest()
    plain = hashlib.shake_256(b'plain'+bytes([i])).digest(length)
    aad = hashlib.shake_256(b'aad'+bytes([i])).digest(i % 31)
    nonce = (0, 1, 0x0102030405060708, (1 << 64)-1)[i % 4]
    cipher = ChaCha20Poly1305(key).encrypt(bytes(4)+nonce.to_bytes(8, 'little'), plain, aad)
    for prefix, value in (('key',key),('plain',plain),('aad',aad),('cipher',cipher)):
        data += array(prefix+str(i), value)
    rows.append('{%d,%d,UINT64_C(0x%x),key%d,plain%d,aad%d,cipher%d}' % (length,len(aad),nonce,i,i,i,i))
data += array('rfc_stream', bytes.fromhex(
    '76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7'
    'da41597c5157488d7724e03fb8d84a376a43b8f41518a11cc387b669b2ee6586'))
data += array('rfc_poly_key', bytes.fromhex('85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b'))
data += array('rfc_poly_tag', bytes.fromhex('a8061dc1305136c6c22b8baf0c0127a9'))
data += array('rfc_poly_msg', b'Cryptographic Forum Research Group')

head = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "crypto/refc/chacha20.h"
#include "crypto/refc/chacha20poly1305.h"
#include "crypto/refc/poly1305-donna.h"
struct fixture {size_t n,adlen;uint64_t nonce;const uint8_t *key,*plain,*aad,*cipher;};
'''
body = r'''
static void guard(const uint8_t *buffer,size_t offset,size_t length,size_t total){
 for(size_t i=0;i<offset;i++)assert(buffer[i]==0xa5);
 for(size_t i=offset+length;i<total;i++)assert(buffer[i]==0xa5);
}
int main(void){
 uint8_t zero[64]={0},stream[64];struct chacha20_ctx ctx;
 chacha20_init(&ctx,zero,0);chacha20(&ctx,stream,zero,64);assert(!memcmp(stream,rfc_stream,64));
 poly1305_context poly;uint8_t tag[16];poly1305_init(&poly,rfc_poly_key);
 for(size_t i=0;i<34;i+=2)poly1305_update(&poly,rfc_poly_msg+i,2);
 poly1305_finish(&poly,tag);assert(!memcmp(tag,rfc_poly_tag,16));
 for(unsigned i=0;i<sizeof cases/sizeof cases[0];i++)for(unsigned shift=0;shift<4;shift++){
  const struct fixture *f=&cases[i];uint8_t out[1600+32],inplace[1600+32],bad[1600+32];
  size_t offset=8+shift;uint8_t *dst=out+offset;const uint8_t *ad=f->adlen?f->aad:NULL;
  memset(out,0xa5,sizeof out);
  chacha20poly1305_encrypt(dst,f->n?f->plain:NULL,f->n,ad,f->adlen,f->nonce,f->key);
  assert(!memcmp(dst,f->cipher,f->n+16));guard(out,offset,f->n+16,sizeof out);
  memset(inplace,0xa5,sizeof inplace);memcpy(inplace+offset,f->plain,f->n);
  chacha20poly1305_encrypt(inplace+offset,inplace+offset,f->n,ad,f->adlen,f->nonce,f->key);
  assert(!memcmp(inplace+offset,f->cipher,f->n+16));guard(inplace,offset,f->n+16,sizeof inplace);
  memset(out,0xa5,sizeof out);assert(chacha20poly1305_decrypt(dst,f->cipher,f->n+16,ad,f->adlen,f->nonce,f->key));
  assert(!memcmp(dst,f->plain,f->n));guard(out,offset,f->n,sizeof out);
  assert(chacha20poly1305_decrypt(inplace+offset,inplace+offset,f->n+16,ad,f->adlen,f->nonce,f->key));
  assert(!memcmp(inplace+offset,f->plain,f->n));
  for(unsigned pos=0;pos<16;pos++){
   memcpy(bad+offset,f->cipher,f->n+16);bad[offset+f->n+pos]^=1;memset(out,0xa5,sizeof out);
   assert(!chacha20poly1305_decrypt(dst,bad+offset,f->n+16,ad,f->adlen,f->nonce,f->key));
   guard(out,0,0,sizeof out); /* failed authentication releases no plaintext */
  }
  memset(out,0xa5,sizeof out);
  assert(!chacha20poly1305_decrypt(dst,f->cipher,f->n+16,ad,f->adlen,f->nonce^1,f->key));guard(out,0,0,sizeof out);
  uint8_t wrong_key[32];memcpy(wrong_key,f->key,32);wrong_key[0]^=1;
  assert(!chacha20poly1305_decrypt(dst,f->cipher,f->n+16,ad,f->adlen,f->nonce,wrong_key));guard(out,0,0,sizeof out);
  if(f->n){
   memcpy(bad+offset,f->cipher,f->n+16);bad[offset]^=1;
   assert(!chacha20poly1305_decrypt(dst,bad+offset,f->n+16,ad,f->adlen,f->nonce,f->key));guard(out,0,0,sizeof out);
  }
  uint8_t wrong_ad[32]={0};memcpy(wrong_ad,f->aad,f->adlen);wrong_ad[0]^=1;
  assert(!chacha20poly1305_decrypt(dst,f->cipher,f->n+16,wrong_ad,f->adlen?f->adlen:1,f->nonce,f->key));guard(out,0,0,sizeof out);
  for(size_t short_len=0;short_len<16;short_len++){
   assert(!chacha20poly1305_decrypt(dst,f->cipher,short_len,ad,f->adlen,f->nonce,f->key));guard(out,0,0,sizeof out);
  }
 }
 puts("PASS: actual crypto RFC KATs, 22 independent AEAD fixtures x4 alignments, in-place, tag/cipher/key/nonce/AAD failures, short input and plaintext-release guards (host)");
}
'''

with tempfile.TemporaryDirectory(prefix='wg-hotloop-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(head+data+'static const struct fixture cases[]={'+','.join(rows)+'};\n'+body,encoding='utf-8')
    (path/'sdkconfig.h').write_text('#define CONFIG_IDF_TARGET_ESP32S3 1\n')
    (path/'esp_attr.h').write_text('#define IRAM_ATTR __attribute__((section(".iram1.hostfixture")))\n')
    flags = ['-std=gnu11','-O2','-Wall','-Wextra','-Wno-sign-compare','-I',str(path),'-I',str(WG)]
    if os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    sources = [WG/'crypto.c', *(WG/'crypto/refc'/name for name in ('chacha20.c','poly1305-donna.c','chacha20poly1305.c'))]
    for mode in ('portable','esp-attribute-fixture'):
        binary = path/('test-'+mode+('.exe' if os.name=='nt' else ''))
        subprocess.run([os.environ.get('CC','gcc'),*flags,
            *(['-DESP_PLATFORM=1'] if mode=='esp-attribute-fixture' else []),str(path/'test.c'),
            *(str(s) for s in sources),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True,timeout=30)
