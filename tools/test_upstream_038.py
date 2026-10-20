"""Execute real C fragments from the 0.1.34..0.1.38 ports, with synthetic I/O.

No device, Internet or real credentials. UPSTREAM_SANITIZE=1 enables ASan/UBSan.
These are regression fixtures, not real TLS/DERP/roam certification.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
WG = ML / 'components/wireguard_lwip/src'


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2] + '\n'


HEAD = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
typedef int esp_err_t;
#define ESP_OK 0
'''


def run(name, program, *, sources=(), includes=(), flags=(), libraries=()):
    with tempfile.TemporaryDirectory(prefix='upstream-038-') as directory:
        path = Path(directory)
        source = path / 'test.c'
        source.write_text(HEAD + program, encoding='utf-8')
        output = path / ('test.exe' if os.name == 'nt' else 'test')
        options = ['-std=c11', '-Wall', '-Wextra', '-Werror', *flags]
        for include in includes:
            options += ['-I', str(include)]
        if os.environ.get('UPSTREAM_SANITIZE') == '1':
            options += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *options, str(source),
                        *(str(s) for s in sources), *libraries, '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True, timeout=30)
    print('PASS: ' + name, flush=True)


wg = (WG / 'wireguard.c').read_text(encoding='utf-8')
replay = function(wg, 'bool wireguard_check_replay(')
run('actual 64-bit replay window: duplicates, reordering, large jumps and rejection limit', r'''
#define REJECT_AFTER_MESSAGES (UINT64_MAX - 8192)
struct wireguard_keypair { uint64_t replay_counter; uint32_t replay_bitmap; };
''' + replay + r'''
int main(void) {
 struct wireguard_keypair k={0};
 assert(wireguard_check_replay(&k,0));assert(!wireguard_check_replay(&k,0));
 assert(wireguard_check_replay(&k,3));assert(wireguard_check_replay(&k,2));
 assert(!wireguard_check_replay(&k,2));
 assert(wireguard_check_replay(&k,((uint64_t)1<<32)+3));
 assert(!wireguard_check_replay(&k,3));assert(!wireguard_check_replay(&k,2));
 assert(wireguard_check_replay(&k,REJECT_AFTER_MESSAGES-1));
 uint64_t saved=k.replay_counter;uint32_t bitmap=k.replay_bitmap;
 assert(!wireguard_check_replay(&k,REJECT_AFTER_MESSAGES));
 assert(!wireguard_check_replay(&k,UINT64_MAX));
 assert(k.replay_counter==saved&&k.replay_bitmap==bitmap);
 for(unsigned i=0;i<10000;i++)assert(!wireguard_check_replay(&k,i));
}
''')

expiry = ''.join(function(wg, signature) for signature in (
    'bool wireguard_keypair_expired(', 'void wireguard_destroy_handshake(',
    'void wireguard_expire_handshake(', 'void wireguard_expire_keys('))
run('actual current/previous/next key expiration and abandoned handshake cleanup', r'''
#define REJECT_AFTER_TIME 180
#define REJECT_AFTER_MESSAGES (UINT64_MAX - 8192)
struct wireguard_keypair {bool valid;uint32_t keypair_millis;uint64_t sending_counter;};
struct handshake {bool valid;uint32_t created_millis;};
struct wireguard_peer {struct handshake handshake;uint8_t handshake_mac1[16];bool handshake_mac1_valid;
 struct wireguard_keypair curr_keypair,prev_keypair,next_keypair;};
static uint32_t now_ms=1000000;
static bool wireguard_expired(uint32_t start,unsigned seconds){return now_ms-start>=seconds*1000;}
static void crypto_zero(void *p,size_t n){memset(p,0,n);}
static void keypair_destroy(struct wireguard_keypair *p){memset(p,0,sizeof *p);}
''' + expiry + r'''
int main(void){
 struct wireguard_peer p={0};
 p.curr_keypair=(struct wireguard_keypair){true,now_ms-1000,0};
 p.prev_keypair=(struct wireguard_keypair){true,now_ms-181000,0};
 p.next_keypair=(struct wireguard_keypair){true,now_ms-1000,REJECT_AFTER_MESSAGES};
 p.handshake=(struct handshake){true,now_ms-541000};
 memset(p.handshake_mac1,99,sizeof p.handshake_mac1);p.handshake_mac1_valid=true;
 wireguard_expire_keys(&p);
 assert(p.curr_keypair.valid&&!p.prev_keypair.valid&&!p.next_keypair.valid);
 assert(!p.handshake.valid&&!p.handshake_mac1_valid);
 for(unsigned i=0;i<sizeof p.handshake_mac1;i++)assert(!p.handshake_mac1[i]);
}
''')

run('actual X25519 ignores coordinate bit 255 in RFC-compatible clamped mode', r'''
#include "x25519.h"
int main(void){
 uint8_t scalar[32],point[32],high[32],a[32],b[32];uint32_t seed=1;
 for(unsigned sample=0;sample<64;sample++){
  for(unsigned i=0;i<32;i++){seed=seed*1664525u+1013904223u;scalar[i]=(uint8_t)(seed>>24);
   seed=seed*1664525u+1013904223u;point[i]=(uint8_t)(seed>>24);}
  point[31]&=127;memcpy(high,point,32);high[31]|=128;
  int ar=x25519(a,scalar,point,1),br=x25519(b,scalar,high,1);
  assert(ar==br&&!memcmp(a,b,32));
 }
}
''', sources=(WG/'crypto/refc/x25519.c',), includes=(WG/'crypto/refc',),
    # The implementation passes a one-limb coefficient with an explicit limb
    # count to mul(); its fe-typed argument triggers a GCC size heuristic even
    # though that count bounds every access. Keep sanitizers enabled.
    flags=('-DBYTE_ORDER=1234', '-DLITTLE_ENDIAN=1234', '-Wno-error=stringop-overread'))

coord = (ML / 'src/ml_coord.c').read_text(encoding='utf-8')
decode = function(coord, 'static int hex_nybble_early(') + function(coord, 'static int hex_to_bytes(')
recv = function(coord, 'static int coord_recv(')
run('actual coordinator read: orderly close, partial stall deadline, progress and exact key decoding', r'''
#define ML_COORD_PARTIAL_READ_MS 5000
#define pdMS_TO_TICKS(x) (x)
typedef struct {int unused;} microlink_t;
static int values[64],offset,count;static int64_t clock_us;
static int64_t esp_timer_get_time(void){return clock_us;}
static void vTaskDelay(int ticks){clock_us+=(int64_t)ticks*1000;}
static int ml_conn_read(microlink_t *ml,uint8_t *buf,size_t length){
 (void)ml;clock_us+=1000000;
 int n=offset<count?values[offset++]:-1;
 if(n<0){errno=EAGAIN;return -1;}if(n>0){assert((size_t)n<=length);memset(buf,7,n);}return n;
}
''' + decode + recv + r'''
static void scenario(int first,int second){offset=0;count=2;values[0]=first;values[1]=second;clock_us=0;}
int main(void){
 uint8_t buffer[8];microlink_t ml={0};
 scenario(0,0);errno=EAGAIN;assert(coord_recv(&ml,buffer,3)<0&&errno==ENOTCONN);
 scenario(-1,-1);assert(coord_recv(&ml,buffer,3)<0&&errno==EAGAIN&&offset==1);
 scenario(1,-1);assert(coord_recv(&ml,buffer,3)<0&&errno==ETIMEDOUT&&clock_us<9000000);
 scenario(1,2);assert(coord_recv(&ml,buffer,3)==0);
 char key[65];memset(key,'a',64);key[64]=0;uint8_t decoded[32];
 assert(hex_to_bytes(key,decoded,32)==32);
 uint8_t saved[32];memcpy(saved,decoded,32);key[63]='z';
 assert(hex_to_bytes(key,decoded,32)==-1&&!memcmp(saved,decoded,32));
 key[63]=0;assert(hex_to_bytes(key,decoded,32)==-1);
 assert(hex_to_bytes(NULL,decoded,32)==-1&&hex_to_bytes(key,NULL,32)==-1);
}
''')

noise = coord.split('    /* Copy entire body to working buffer', 1)[1]
noise = '    /* Copy entire body to working buffer' + noise.split('    int msg2_total =', 1)[0]
run('actual Noise msg2 header buffer bounds and exact 48-byte IK reply length', r'''
static uint8_t header[3];static unsigned received;
static void *ml_psram_malloc(size_t n){assert(n>=512);return malloc(n);}
static int coord_recv(void *ml,uint8_t *p,size_t n){
 (void)ml;assert(received+n<=3);memcpy(p,header+received,n);received+=(unsigned)n;return 0;
}
static int verify(int body_len){
 void *ml=NULL;uint8_t *resp=calloc(1,body_len?body_len:1);assert(resp);
 uint8_t *body_start=resp;memcpy(resp,header,body_len<3?(size_t)body_len:3);
 received=body_len<3?(unsigned)body_len:3;
''' + noise + r'''
 (void)payload_len;free(body_buf);return 0;
}
int main(void){
 for(int length=0;length<80;length++){
  header[0]=2;header[1]=0;header[2]=48;assert(verify(length)==0);
  header[2]=47;assert(verify(length)==-1);header[2]=49;assert(verify(length)==-1);
  header[0]=1;header[2]=48;assert(verify(length)==-1);
 }
}
''')

derp = (ML / 'src/ml_derp.c').read_text(encoding='utf-8')
tls = '    bool verify_tls =' + derp.split('    bool verify_tls =', 1)[1].split('    mbedtls_ssl_conf_rng(', 1)[0]
run('actual DERP TLS policy: trusted verification default, CertName and CA-attach failure without fallback', r'''
#define MBEDTLS_SSL_VERIFY_REQUIRED 2
#define MBEDTLS_SSL_VERIFY_NONE 0
typedef struct {bool insecure_for_tests;char cert_name[80];} ml_derp_node_t;
typedef struct {struct {int ssl_conf;} derp;} microlink_t;
static int mode,attach_error,attaches;
static void mbedtls_ssl_conf_authmode(int *conf,int value){(void)conf;mode=value;}
static int esp_crt_bundle_attach(int *conf){(void)conf;attaches++;return attach_error;}
static int configure(ml_derp_node_t *derp_node,const char *derp_host){
 microlink_t node={0};microlink_t *ml=&node;
''' + tls + r'''
 assert(!strcmp(tls_name,derp_node&&derp_node->cert_name[0]?derp_node->cert_name:derp_host));
 return 0;fail_tls:return -1;
}
int main(void){
 assert(!configure(NULL,"relay.example")&&mode==2&&attaches==1);
 ml_derp_node_t node={0};strcpy(node.cert_name,"certificate.example");
 assert(!configure(&node,"relay.example")&&mode==2&&attaches==2);
 attach_error=1;assert(configure(&node,"relay.example")==-1&&mode==2);
 attach_error=0;node.insecure_for_tests=true;int before=attaches;
 assert(!configure(&node,"relay.example")&&mode==0&&attaches==before);
}
''')

mgr = (ML / 'src/ml_wg_mgr.c').read_text(encoding='utf-8')
sync = 'struct wg_tcpip_call {' + mgr.split('struct wg_tcpip_call {', 1)[1].split('static void wg_netif_bring_up_cb', 1)[0]
run('actual blocking TCPIP executor completes callback before its stack context expires', r'''
static unsigned completions;
static int esp_netif_tcpip_exec(int(*fn)(void*),void *arg){return fn(arg);}
''' + sync + r'''
static void callback(void *p){(*(unsigned *)p)++;completions++;}
int main(void){unsigned count=0;for(unsigned i=0;i<10000;i++){wg_tcpip_sync(callback,&count);assert(count==i+1&&completions==count);}}
''')

wireif = (WG / 'wireguardif.c').read_text(encoding='utf-8')
assert 'esp_netif_tcpip_exec(wg_tcpip_exec_wrap, &c)' in mgr
for cb in ('wg_netif_init_cb', 'wg_netif_bring_up_cb', 'wg_udp_pcb_create_cb', 'wg_netif_take_down_cb'):
    assert 'wg_tcpip_sync(' + cb in mgr
x25519 = (WG/'crypto/refc/x25519.c').read_text()
assert 'x1i[NLIMBS - 1] &=' in x25519 and 'x1 = (const uint8_t *)x1i;' in x25519
assert 'wireguard_keypair_expired(keys[i])' in wg and 'wireguard_expire_handshake(peer)' in wg
encrypt = wireif.split('U64TO8_LITTLE(hdr->counter, keypair->sending_counter)', 1)[0]
assert encrypt.rfind('xSemaphoreTake(s_wg_tx_lock') > encrypt.rfind('if (pbuf)')
after = wireif.split('U64TO8_LITTLE(hdr->counter, keypair->sending_counter)', 1)[1]
assert after.index('wireguard_encrypt_packet(') < after.index('xSemaphoreGive(s_wg_tx_lock)')
assert 'peer->last_data_tx = 0;' in wireif and 'peer->last_direct_rx' in wireif
assert 'tx_pbuf_alloc_fn(out_len' in wireif and 'wg_tx_pbuf_alloc_cb' in mgr
assert 'ml->state = ML_STATE_ERROR;' in (ML/'src/microlink.c').read_text()
netcheck = (ML/'src/ml_netcheck.c').read_text()
assert netcheck.count('drain_replies(ml, sock, probes, probe_count,') >= 3
assert 'NETCHECK_SAMPLES' in netcheck and 'derp_rtt_ms' in netcheck
assert 'PreferredDERP' in coord and 'derp_home_region' in coord
print('PASS: upstream lifecycle/rekey/copy-free hooks and fork direct-reply state preserved', flush=True)

web = (ROOT/'main/web_ui.c').read_text(encoding='utf-8')
handler = function(web, 'static esp_err_t system_debug_wg_tx_post_handler(')
cjson = os.environ.get('CJSON_SOURCE')
run('actual WG TX HTTP diagnostic: password session, strict JSON, lifecycle contention and failed mutations', r'''
#include "cJSON.h"
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE -3
#define HTTPD_400_BAD_REQUEST 400
typedef struct {const char *body;int status;char response[256];} httpd_req_t;
struct microlink_s {int unused;};
static struct microlink_s node;
static bool auth=true,busy,missing,held,copyfree=true;
static unsigned mutations,resets;static uint32_t packets=17;static uint64_t micros=100;
static int require_password_session(httpd_req_t *r){if(auth)return 0;r->status=401;return -1;}
static int recv_body(httpd_req_t *r,char *to,size_t cap,void *unused){
 (void)unused;size_t n=strlen(r->body);if(n>=cap){r->status=413;return -1;}memcpy(to,r->body,n+1);return 0;
}
static int httpd_resp_send_err(httpd_req_t *r,int status,const char *s){(void)s;r->status=status;return 0;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);return 0;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){snprintf(r->response,sizeof r->response,"%s",s);return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;assert(!strcmp(s,"application/json"));return 0;}
static bool tailscale_lifecycle_try_acquire(void){assert(!held);if(busy)return false;held=true;return true;}
static void tailscale_lifecycle_release(void){assert(held);held=false;}
static struct microlink_s *tailscale_get_microlink(void){assert(held);return missing?NULL:&node;}
static int microlink_set_wg_tx_copyfree(struct microlink_s *n,bool v){mutations++;if(!n)return -3;copyfree=v;return 0;}
static bool microlink_get_wg_tx_copyfree(struct microlink_s *n){return n&&copyfree;}
static void microlink_get_wg_tx_profile(uint32_t *p,uint64_t *us,bool reset){
 if(p)*p=packets;if(us)*us=micros;if(reset){resets++;packets=0;micros=0;}
}
''' + handler + r'''
static httpd_req_t request(const char *body,int expected){
 httpd_req_t r={body,200,{0}};system_debug_wg_tx_post_handler(&r);assert(r.status==expected&&!held);return r;
}
int main(void){
 auth=false;request("{\"copyfree\":false}",401);assert(!mutations);auth=true;
 const char *bad[]={"null","[]","{}","{","{\"copyfree\":0}","{\"reset\":\"true\"}","{\"copyfree\":null}"};
 for(unsigned i=0;i<sizeof bad/sizeof *bad;i++)request(bad[i],400);
 assert(!mutations&&!resets);
 busy=true;request("{\"copyfree\":false,\"reset\":true}",503);busy=false;assert(!mutations&&!resets);
 missing=true;request("{\"copyfree\":true,\"reset\":true}",409);missing=false;assert(mutations==1&&!resets);
 httpd_req_t r=request("{\"copyfree\":false,\"reset\":true}",200);
 assert(!copyfree&&resets==1);cJSON *root=cJSON_Parse(r.response);assert(root);
 assert(cJSON_IsTrue(cJSON_GetObjectItem(root,"ok"))&&cJSON_IsFalse(cJSON_GetObjectItem(root,"copyfree")));
 assert(cJSON_GetObjectItem(root,"pkts")->valueint==0);cJSON_Delete(root);
 request("{\"copyfree\":true}",200);assert(copyfree&&mutations==3);
}
''', sources=(Path(cjson),) if cjson else (),
    includes=(Path(cjson).parent,) if cjson else ('/usr/include/cjson',),
    libraries=() if cjson else ('-lcjson',), flags=('-Wno-misleading-indentation',))
