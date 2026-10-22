"""Actual coordinator/policy/manager C with synthetic queue/NVS/WG install sink.

Tests bounded cache convergence, not crypto, FreeRTOS scheduling or real clients.
POLICY_SANITIZE=1 / POLICY_NO_PIE=1 have the same meaning as the policy driver.
"""
import ast
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ML=ROOT/'external/microlink/components/microlink'


def constant(name):
    tree=ast.parse((ROOT/'tools/test_tailnet_authorization.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))


def function(source,signature):
    start=source.index(signature)
    return source[start:source.index('\n}',start)+2]+'\n'


coord=(ML/'src/ml_coord.c').read_text(encoding='utf-8')
manager=(ML/'src/ml_wg_mgr.c').read_text(encoding='utf-8')
internal=(ML/'include/microlink_internal.h').read_text(encoding='utf-8')
start=internal.index('typedef struct {\n    enum {\n        ML_PEER_ADD,')
update=internal[start:internal.index('} ml_peer_update_t;',start)+len('} ml_peer_update_t;')]
parser=function(coord,'static bool parse_peers_from_map_response(') if 'static bool parse_peers_from_map_response(' in coord else function(coord,'static void parse_peers_from_map_response(')
apply_map=function(coord,'static bool apply_peer_map(') if 'static bool apply_peer_map(' in coord else '''
/* Baseline reproduction only: old coordinator had separate unguarded calls. */
static bool apply_peer_map(microlink_t *ml,cJSON *map){if(!ml_policy_apply(map))return false;parse_peers_from_map_response(ml,map);return true;}
'''

HEAD=r'''
#include <stdarg.h>
#define ML_MAX_PEERS 16
#define ML_MAX_ENDPOINTS 8
#define MICROLINK_MAX_PEER_ROUTES 8
#define pdTRUE 1
#define pdMS_TO_TICKS(n) (n)
static const char *TAG="synthetic";
static void log_sink(const char *tag,const char *fmt,...){(void)tag;(void)fmt;}
#define ESP_LOGI(...) log_sink(__VA_ARGS__)
#define ESP_LOGW(...) log_sink(__VA_ARGS__)
#define ESP_LOGE(...) log_sink(__VA_ARGS__)
typedef uint8_t u8_t;
typedef struct {uint32_t network;uint8_t prefix_len;} microlink_route_t;
'''+update+r'''
typedef struct {
    bool active,online;uint8_t public_key[32];char hostname[64];uint32_t vpn_ip;
    uint64_t node_id;int wg_peer_index,endpoint_count;uint16_t derp_region;
    struct {uint32_t ip;uint16_t port;bool is_ipv6;} endpoints[ML_MAX_ENDPOINTS];
} ml_peer_t;
typedef struct {ml_peer_update_t *items[256];unsigned head,tail;} queue;
typedef struct {ml_peer_t peers[ML_MAX_PEERS];int peer_count;void *peer_update_queue,*wg_netif;} microlink_t;
struct netif {unsigned dummy;};
static unsigned calls,fail_alloc,fail_send,send_calls,rejected_adds,cache_removes,wg_removes;
static bool sync_fail;
void *peer_sync_test_alloc(size_t n){return sync_fail?NULL:calloc(1,n);}
#define ML_PEER_SYNC_HOST_TEST 1
#include "ml_peer_sync.c"
static void *ml_psram_calloc(size_t n,size_t size){calls++;return calls==fail_alloc?NULL:calloc(n,size);}
static int xQueueSend(void *handle,const void *item,unsigned ticks){
    (void)ticks;queue *q=handle;send_calls++;if(send_calls==fail_send)return 0;
    assert(q->tail<256);q->items[q->tail++]=*(ml_peer_update_t *const *)item;return pdTRUE;
}
static int xQueueReceive(void *handle,void *item,unsigned ticks){
    (void)ticks;queue *q=handle;if(q->head==q->tail)return 0;
    *(ml_peer_update_t **)item=q->items[q->head++];return pdTRUE;
}
static int hex_to_bytes(const char *s,uint8_t *out,size_t n){
    if(!s||strlen(s)!=n*2)return -1;
    for(size_t i=0;i<n;i++){unsigned value=0;for(unsigned j=0;j<2;j++){
        unsigned c=(unsigned char)s[2*i+j],v=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:99;
        if(v>15)return -1;value=value*16+v;}out[i]=value;}return (int)n;
}
static void microlink_ip_to_str(uint32_t ip,char *out){snprintf(out,16,"%u.%u.%u.%u",ip>>24,(ip>>16)&255,(ip>>8)&255,ip&255);}
static void ml_peer_nvs_remove(const uint8_t *key){(void)key;cache_removes++;}
static int wireguardif_remove_peer(struct netif *n,u8_t slot){(void)n;assert(slot<16);wg_removes++;return 0;}
'''

finders=function(manager,'static int find_peer_by_key(')+function(manager,'static int find_peer_by_node_id(')
SINK=r'''
/* Only WG installation is replaced: explicit bounded sink, not actual crypto. */
static int add_peer(microlink_t *ml,const ml_peer_update_t *u){
    int idx=find_peer_by_key(ml,u->public_key);
    if(idx<0)for(unsigned i=0;i<16;i++)if(!ml->peers[i].active){idx=(int)i;break;}
    if(idx<0){rejected_adds++;return -1;}
    ml_peer_t *p=&ml->peers[idx];p->active=true;memcpy(p->public_key,u->public_key,32);
    p->vpn_ip=u->vpn_ip;p->node_id=u->node_id;p->wg_peer_index=idx;
    p->endpoint_count=u->endpoint_count;memcpy(p->endpoints,u->endpoints,sizeof p->endpoints);p->derp_region=u->derp_region;
    if(u->has_online)p->online=u->online;
    if(idx>=ml->peer_count)ml->peer_count=idx+1;return idx;
}
'''
remove=function(manager,'static void remove_peer(')
prune=function(manager,'static void prune_peer_cache(') if 'static void prune_peer_cache(' in manager else ''
process=function(manager,'static void process_peer_updates(')

TESTS=r'''
static cJSON *peer_json(unsigned id,unsigned address){
    char key[80],ip[40];snprintf(key,sizeof key,"nodekey:%064x",id);snprintf(ip,sizeof ip,"100.64.1.%u/32",address);
    cJSON *p=cJSON_CreateObject();assert(p);assert(cJSON_AddNumberToObject(p,"ID",id));
    assert(cJSON_AddStringToObject(p,"Key",key));cJSON *ips=cJSON_AddArrayToObject(p,"Addresses");
    assert(ips&&cJSON_AddItemToArray(ips,cJSON_CreateString(ip)));return p;
}
static cJSON *full(unsigned offset){
    cJSON *map=cJSON_Parse("{" NODE ",\"PacketFilter\":[" ALL_RULE "]}");assert(map);
    cJSON *peers=cJSON_AddArrayToObject(map,"Peers");assert(peers);
    for(unsigned id=1+offset;id<=16+offset;id++)assert(cJSON_AddItemToArray(peers,peer_json(id,id)));
    return map;
}
static void drain(microlink_t *ml){process_peer_updates(ml);queue *q=ml->peer_update_queue;assert(q->head==q->tail);q->head=q->tail=0;}
static void seed(microlink_t *ml,queue *q){
    ml_policy_reset();memset(ml,0,sizeof *ml);memset(q,0,sizeof *q);ml->peer_update_queue=q;ml->wg_netif=ml;
    calls=send_calls=fail_alloc=fail_send=rejected_adds=cache_removes=wg_removes=0;
    cJSON *map=full(0);assert(apply_peer_map(ml,map));cJSON_Delete(map);drain(ml);assert(ml->peer_count==16);
    calls=send_calls=cache_removes=wg_removes=0;
}
static void capacity(void){
    microlink_t ml;queue q;seed(&ml,&q);cJSON *map=full(1);assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
    uint8_t key[32]={[31]=17};assert(find_peer_by_key(&ml,key)>=0);
    key[31]=1;assert(find_peer_by_key(&ml,key)<0);assert(!rejected_adds);
    assert(cache_removes==1&&wg_removes==1);
    /* Known-empty authority must prune even if no remove job can be queued. */
    map=cJSON_Parse("{\"Peers\":[]}");assert(map);assert(ml_policy_apply(map));cJSON_Delete(map);
    drain(&ml);assert(ml.peer_count==0);
    puts("PASS: actual parser/manager reconcile full-table replacement and known-empty map without extra slots/removal allocation (WG/NVS sink)");
}
static void stale(void){
    microlink_t ml;queue q;seed(&ml,&q);
    cJSON *map=full(1);assert(ml_policy_apply(map));cJSON_Delete(map);
    ml_peer_update_t *old=calloc(1,sizeof *old);assert(old);old->action=ML_PEER_ADD;old->has_node_id=true;old->node_id=1;old->public_key[31]=1;
    assert(xQueueSend(&q,&old,0));drain(&ml);uint8_t key[32]={[31]=1};assert(find_peer_by_key(&ml,key)<0);
    ml_peer_update_t *rm=calloc(1,sizeof *rm);assert(rm);rm->action=ML_PEER_REMOVE;rm->has_node_id=true;rm->node_id=2;
    assert(xQueueSend(&q,&rm,0));drain(&ml);key[31]=2;assert(find_peer_by_key(&ml,key)>=0);
    /* Keepalive payload cannot enqueue peer/filter mutations. */
    unsigned before=send_calls;map=cJSON_Parse("{\"KeepAlive\":true,\"Peers\":[],\"PeersRemoved\":[2]}");assert(map);
    assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);assert(send_calls==before&&find_peer_by_key(&ml,key)>=0);
    /* No current authority means retain the fast-boot cache, NOT grant traffic. */
    ml_policy_reset();int count=ml.peer_count;drain(&ml);assert(ml.peer_count==count);
    assert(!rx(4,6,"100.64.1.2","100.64.0.10",40000,80,2,key));
    puts("PASS: actual manager rejects obsolete queued add/remove; keepalive no mutation; unknown policy retains cache but denies packets");
}
static void faults(void){
    for(unsigned fail=1;fail<=16;fail++)for(unsigned kind=0;kind<2;kind++){
        microlink_t ml;queue q;seed(&ml,&q);if(kind)fail_send=fail;else fail_alloc=fail;
        cJSON *map=full(1);assert(!apply_peer_map(&ml,map));cJSON_Delete(map);
        uint8_t key[32]={[31]=2};assert(!rx(4,6,"100.64.1.2","100.64.0.10",40000,80,2,key));
        fail_alloc=fail_send=0;drain(&ml);map=full(1);assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
        key[31]=17;assert(find_peer_by_key(&ml,key)>=0);key[31]=1;assert(find_peer_by_key(&ml,key)<0);
    }
    puts("PASS: actual map application propagates every one of 16 allocation/queue failures, blocks data and converges after a valid retry");
}
static void semantics(void){
    microlink_t ml;queue q;seed(&ml,&q);
    /* At capacity, numeric removal is applied before the replacement add. */
    cJSON *map=cJSON_Parse("{\"Peers\":[],\"PeersRemoved\":[1],\"PeersChanged\":[]}");assert(map);
    assert(cJSON_AddItemToArray(cJSON_GetObjectItem(map,"PeersChanged"),peer_json(17,17)));
    assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
    uint8_t key[32]={[31]=17};assert(find_peer_by_key(&ml,key)>=0);
    key[31]=1;assert(find_peer_by_key(&ml,key)<0);key[31]=2;assert(find_peer_by_key(&ml,key)>=0);
    assert(!rejected_adds);
    /* An upsert for a removed NodeID wins; the late removal job must not evict it. */
    map=cJSON_Parse("{\"Peers\":null,\"PeersRemoved\":[2],\"PeersChanged\":[]}");assert(map);
    cJSON *replacement=peer_json(2,18);assert(cJSON_ReplaceItemInObject(replacement,"Key",cJSON_CreateString("nodekey:0000000000000000000000000000000000000000000000000000000000000012")));
    assert(cJSON_AddItemToArray(cJSON_GetObjectItem(map,"PeersChanged"),replacement));
    assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
    key[31]=2;assert(find_peer_by_key(&ml,key)<0);key[31]=18;assert(find_peer_by_key(&ml,key)>=0);
    /* Full nonempty Peers overrides otherwise contradictory peer deltas. */
    map=full(1);cJSON *removed=cJSON_AddArrayToObject(map,"PeersRemoved");assert(removed&&cJSON_AddItemToArray(removed,cJSON_CreateNumber(2)));
    cJSON *changed=cJSON_AddArrayToObject(map,"PeersChanged");assert(changed&&cJSON_AddItemToArray(changed,peer_json(18,18)));
    cJSON *patches=cJSON_AddArrayToObject(map,"PeersChangedPatch"),*patch=cJSON_CreateObject();assert(patches&&patch);
    assert(cJSON_AddNumberToObject(patch,"NodeID",2)&&cJSON_AddBoolToObject(patch,"Expired",true)&&cJSON_AddItemToArray(patches,patch));
    assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
    key[31]=2;assert(find_peer_by_key(&ml,key)>=0);key[31]=18;assert(find_peer_by_key(&ml,key)<0);
    assert(!rejected_adds&&ml.peer_count==16);
    puts("PASS: actual coordinator/manager empty-or-null Peers deltas preserve other peers; removed/upserted identity and full-map precedence converge at capacity");
}
static void metadata(void){
    microlink_t ml;queue q;seed(&ml,&q);
    cJSON *map=cJSON_Parse("{\"PeersChanged\":[]}");assert(map);cJSON *p=peer_json(2,2);
    assert(cJSON_AddNumberToObject(p,"HomeDERP",7));assert(cJSON_AddBoolToObject(p,"Online",false));
    cJSON *eps=cJSON_AddArrayToObject(p,"Endpoints");assert(eps&&cJSON_AddItemToArray(eps,cJSON_CreateString("198.51.100.20:2222")));
    assert(cJSON_AddItemToArray(cJSON_GetObjectItem(map,"PeersChanged"),p));assert(apply_peer_map(&ml,map));cJSON_Delete(map);
    map=cJSON_Parse("{\"PeersChangedPatch\":[{\"NodeID\":2,\"Endpoints\":[\"203.0.113.7:4444\"]}]}");assert(apply_peer_map(&ml,map));cJSON_Delete(map);
    map=cJSON_Parse("{\"PeersChangedPatch\":[{\"NodeID\":2,\"Online\":true}]}");assert(apply_peer_map(&ml,map));cJSON_Delete(map);
    /* Deliberate host reordering: every old job must resolve the current merged
     * desired fields, not overwrite a newer delta with its stale snapshot. */
    for(unsigned i=0;i<(q.tail-q.head)/2;i++){ml_peer_update_t *tmp=q.items[q.head+i];q.items[q.head+i]=q.items[q.tail-1-i];q.items[q.tail-1-i]=tmp;}
    drain(&ml);int i=find_peer_by_node_id(&ml,2);assert(i>=0);
    assert(ml.peers[i].endpoint_count==1&&ml.peers[i].endpoints[0].port==4444&&ml.peers[i].derp_region==7&&ml.peers[i].online);
    map=cJSON_Parse("{\"PeersChangedPatch\":[{\"NodeID\":2,\"Endpoints\":[],\"DERPRegion\":0}]}");assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);
    assert(!ml.peers[i].endpoint_count&&!ml.peers[i].derp_region&&ml.peers[i].online);
    ml_peer_update_t u={.action=ML_PEER_UPDATE_ENDPOINT,.has_node_id=true,.node_id=2};
    ml_policy_suspend();assert(!ml_peer_sync_resolve(&u));
    puts("PASS: actual coordinator/mailbox/manager latest full+partial metadata merge, reverse job order, explicit empty/zero clearing, suspended authority refusal (WG/NVS sinks)");
}
static void mailbox_oom(void){
    microlink_t ml={0};queue q={0};ml.peer_update_queue=&q;ml.wg_netif=&ml;sync_fail=true;
    cJSON *map=full(0);assert(!apply_peer_map(&ml,map));cJSON_Delete(map);
    assert(ml_policy_peer_status(key_a)==-1);sync_fail=false;map=full(0);assert(apply_peer_map(&ml,map));cJSON_Delete(map);drain(&ml);assert(ml.peer_count==16);
    puts("PASS: mailbox allocation failure blocks authority; complete retry converges");
}
int main(int argc,char **argv){assert(argc==2);(void)key_a;(void)key_b;
    if(!strcmp(argv[1],"capacity"))capacity();else if(!strcmp(argv[1],"stale"))stale();else if(!strcmp(argv[1],"semantics"))semantics();
    else if(!strcmp(argv[1],"metadata"))metadata();else if(!strcmp(argv[1],"mailbox-oom"))mailbox_oom();else faults();ml_policy_reset();free(sync_entries);sync_entries=NULL;
}
'''

program='#define ML_POLICY_HOST_TEST 1\n#include "ml_policy.c"\n'+constant('HEAD')+HEAD+finders+SINK+remove+prune+process+parser+apply_map+TESTS
with tempfile.TemporaryDirectory(prefix='peer-convergence-') as directory:
    path=Path(directory);(path/'lwip').mkdir();(path/'lwip/pbuf.h').write_text(constant('PBUF'),encoding='utf-8');(path/'test.c').write_text(program,encoding='utf-8')
    flags=['-std=c11','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-O1','-g',
           '-I',str(path),'-I',str(ML/'include'),'-I',str(ML/'src')]
    libs=['-lws2_32'] if os.name=='nt' else ['-lm']
    dep=os.environ.get('CJSON_SOURCE')
    if dep:flags+=['-I',str(Path(dep).parent),dep]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('POLICY_SANITIZE')=='1':
        flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if os.environ.get('POLICY_NO_PIE')=='1' and os.name!='nt':flags+=['-fno-pie','-no-pie']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(path/'test.c'),'-o',str(binary),*libs],check=True)
    errors=[]
    for scenario in ('capacity','stale','faults','semantics','metadata','mailbox-oom'):
        with (path/'run.log').open('w+b') as log:
            try:subprocess.run([str(binary),scenario],check=True,timeout=45,stdout=log,stderr=subprocess.STDOUT)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:errors.append(str(error))
            log.seek(0,2);log.seek(max(0,log.tell()-8192));print(log.read().decode(errors='replace'),end='',flush=True)
    if errors:raise SystemExit('\n'.join(errors))
