/* Private receive-DNAT fragment ownership; SPDX-License-Identifier: MIT */
#include "tailnet_reassembly.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "lwip/tcpip.h"
#include "lwip/ip4_frag.h"
#include "lwip/prot/ip.h"
#include "lwip/inet_chksum.h"
#include "lwip/sys.h"
#include "lwip/timeouts.h"

#define FRAGMENT_LIMIT IP_REASS_MAX_PBUFS
#define DATAGRAM_LIMIT ((FRAGMENT_LIMIT+1)/2)
#if FRAGMENT_LIMIT < 2
#error "Receive DNAT requires at least two reassembly pbufs"
#endif

typedef struct {
    bool used;
    struct netif *input;
    uint32_t source,destination;
    uint16_t id,total;
    uint8_t protocol;
    uint32_t created_ms;
} datagram_t;
typedef struct {
    struct pbuf *packet;
    uint16_t start,end,chains;
    unsigned context;
} fragment_t;
static datagram_t s_datagrams[DATAGRAM_LIMIT];
static fragment_t s_fragments[FRAGMENT_LIMIT];
static unsigned s_pbufs;

static void discard(unsigned context)
{
    for(unsigned i=0;i<FRAGMENT_LIMIT;i++) {
        fragment_t *f=&s_fragments[i];
        if(!f->packet||f->context!=context)continue;
        s_pbufs-=f->chains;pbuf_free(f->packet);memset(f,0,sizeof *f);
    }
    memset(&s_datagrams[context],0,sizeof s_datagrams[context]);
}
static void expire(void *arg)
{
    (void)arg;LWIP_ASSERT_CORE_LOCKED();uint32_t now=sys_now();
    for(unsigned i=0;i<DATAGRAM_LIMIT;i++) {
        if(!s_datagrams[i].used)continue;
        if((uint32_t)(now-s_datagrams[i].created_ms)>=IP_REASS_MAXAGE*IP_TMR_INTERVAL)discard(i);
    }
}
void tailnet_reassembly_refresh(void)
{
    /* sys_timeout can assert if its allocation fails. Never allocate a
     * mandatory per-packet timer; a failed best-effort queue is retried by
     * the manager, and packet-time expiry remains allocation-free. */
    (void)tcpip_try_callback(expire,NULL);
}
static bool evict(int except)
{
    int oldest=-1;
    for(unsigned i=0;i<DATAGRAM_LIMIT;i++)
        if(s_datagrams[i].used&&(int)i!=except&&
           (oldest<0||(uint32_t)(sys_now()-s_datagrams[i].created_ms)>
                        (uint32_t)(sys_now()-s_datagrams[oldest].created_ms)))oldest=(int)i;
    if(oldest<0)return false;
    discard((unsigned)oldest);return true;
}

struct pbuf *tailnet_reassemble(struct pbuf *packet,struct netif *input)
{
    LWIP_ASSERT_CORE_LOCKED();expire(NULL);uint8_t header[20];
    if(!packet)return NULL;
    if(!input||packet->len<20||pbuf_copy_partial(packet,header,20,0)!=20||header[0]!=0x45)goto drop;
    unsigned total=((unsigned)header[2]<<8)|header[3];
    unsigned flags=((unsigned)header[6]<<8)|header[7];
    unsigned start=(flags&IP_OFFMASK)*8;
    if(total<=20||total!=packet->tot_len||(flags&0xc000)||inet_chksum(packet->payload,20))goto drop;
    unsigned length=total-20,end=start+length;
    if(end>65535-20||((flags&IP_MF)&&(length&7)))goto drop;
    uint32_t src,dst;memcpy(&src,header+12,4);memcpy(&dst,header+16,4);
    uint16_t id=((uint16_t)header[4]<<8)|header[5];
    int context=-1;
    for(unsigned i=0;i<DATAGRAM_LIMIT;i++) {
        const datagram_t *d=&s_datagrams[i];
        if(d->used&&d->input==input&&d->source==src&&d->destination==dst&&d->id==id&&d->protocol==header[9]){context=(int)i;break;}
    }
    if(context>=0) {
        const datagram_t *d=&s_datagrams[context];
        if(d->total&&(end>d->total||(!(flags&IP_MF)&&end!=d->total)))goto drop;
        for(unsigned i=0;i<FRAGMENT_LIMIT;i++) {
            const fragment_t *f=&s_fragments[i];
            if(!f->packet||f->context!=(unsigned)context)continue;
            if(start<f->end&&end>f->start)goto drop;
            if(!(flags&IP_MF)&&f->end>end)goto drop;
        }
    }
    unsigned chains=pbuf_clen(packet);
    if(chains>FRAGMENT_LIMIT)goto drop;
    while(s_pbufs+chains>FRAGMENT_LIMIT)if(!evict(context))goto drop;
    if(context<0) {
        for(unsigned i=0;i<DATAGRAM_LIMIT;i++)if(!s_datagrams[i].used){context=(int)i;break;}
        if(context<0) {
            if(!evict(-1))goto drop;
            for(unsigned i=0;i<DATAGRAM_LIMIT;i++)if(!s_datagrams[i].used){context=(int)i;break;}
        }
        if(context<0)goto drop;
        s_datagrams[context]=(datagram_t){.used=true,.input=input,.source=src,.destination=dst,.id=id,.protocol=header[9],.created_ms=sys_now()};
    }
    for(unsigned i=0;i<FRAGMENT_LIMIT;i++)if(!s_fragments[i].packet) {
        s_fragments[i]=(fragment_t){.packet=packet,.start=start,.end=end,.chains=chains,.context=(unsigned)context};
        s_pbufs+=chains;break;
    }
    if(!(flags&IP_MF))s_datagrams[context].total=end;
    unsigned cursor=0,count=0,order[FRAGMENT_LIMIT];
    while(count<FRAGMENT_LIMIT) {
        int next=-1;
        for(unsigned i=0;i<FRAGMENT_LIMIT;i++)
            if(s_fragments[i].packet&&s_fragments[i].context==(unsigned)context&&s_fragments[i].start==cursor){next=(int)i;break;}
        if(next<0)break;
        order[count++]=(unsigned)next;cursor=s_fragments[next].end;
    }
    if(s_datagrams[context].total&&cursor==s_datagrams[context].total&&count) {
        struct pbuf *complete=s_fragments[order[0]].packet;
        for(unsigned i=0;i<count;i++) {
            fragment_t *f=&s_fragments[order[i]];
            if(i){pbuf_remove_header(f->packet,20);pbuf_cat(complete,f->packet);}
            s_pbufs-=f->chains;memset(f,0,sizeof *f);
        }
        memset(&s_datagrams[context],0,sizeof s_datagrams[context]);
        uint8_t *h=complete->payload;unsigned size=cursor+20;
        h[2]=size>>8;h[3]=size;h[6]=h[7]=h[10]=h[11]=0;
        uint16_t sum=inet_chksum(h,20);memcpy(h+10,&sum,2);
        return complete;
    }
    return NULL;
drop:
    pbuf_free(packet);return NULL;
}
