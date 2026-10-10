/* Enforce listener policy where the SDK processes IPv4 input, not at the
 * earlier physical/tunnel callback that queues packets to tcpip_thread.
 * SPDX-License-Identifier: MIT */
#include "tailnet_forward.h"
#include "tailnet_reassembly.h"
#include <string.h>
#include "lwip/tcpip.h"
#include "lwip/ip4.h"
#include "lwip/ip4_frag.h"
#include "lwip/inet_chksum.h"
#include "lwip/prot/ip.h"

err_t __real_ip4_input(struct pbuf *packet, struct netif *input);

static __attribute__((noinline)) struct pbuf *prepare_dnat_packet(struct pbuf *packet,struct netif *input)
{
    uint8_t header[20];
    if(!packet)return NULL;
    if(pbuf_copy_partial(packet,header,sizeof header,0)!=sizeof header)goto drop;
    if((header[0]>>4)!=4||!input||input->napt)return packet;
    uint32_t destination;
    memcpy(&destination,header+16,sizeof destination);
    if(destination!=netif_ip4_addr(input)->addr)return packet;
    unsigned hlen=(header[0]&15)*4;
    unsigned total=((unsigned)header[2]<<8)|header[3];
    unsigned fragment=((unsigned)header[6]<<8)|header[7];
    if(hlen<20||hlen>packet->len||total<hlen||total>packet->tot_len)goto drop;
    if(header[9]!=6&&header[9]!=17)return packet;
    if(total<packet->tot_len)pbuf_realloc(packet,total);
    if(fragment&(IP_OFFMASK|IP_MF)) {
        /* The SDK applies receive DNAT before its normal reassembly step.
         * Never let it treat a later fragment's data as a TCP/UDP header.
         * Use a private pool keyed by input interface, protocol and IP tuple;
         * native local-service fragments must not contaminate this policy. */
#if IP_REASSEMBLY
        packet=tailnet_reassemble(packet,input);
        if(!packet)return NULL; /* Reassembler owns queued/dropped fragments. */
        if(pbuf_copy_partial(packet,header,sizeof header,0)!=sizeof header)goto drop;
        hlen=(header[0]&15)*4;
        total=((unsigned)header[2]<<8)|header[3];
        /* Restore a valid header even if the SDK's checksum generation is
         * disabled; authorization below uses the first fragment's header. */
        ((uint8_t*)packet->payload)[10]=((uint8_t*)packet->payload)[11]=0;
        uint16_t sum=inet_chksum(packet->payload,hlen);
        memcpy((uint8_t*)packet->payload+10,&sum,sizeof sum);
#else
        goto drop;
#endif
    }
    unsigned minimum=hlen+(header[9]==6?20:8);
    if(total<minimum||packet->tot_len<minimum)goto drop;
    /* SDK NAPT accesses and rewrites transport headers directly in the first
     * pbuf. A valid small first fragment or split header must be made safe. */
    if(packet->len<minimum)packet=pbuf_coalesce(packet,PBUF_RAW);
    if(!packet)return NULL;
    if(packet->len<minimum)goto drop; /* coalesce can return the old chain on OOM */
    const uint8_t *transport=(const uint8_t*)packet->payload+hlen;
    if(header[9]==6) {
        unsigned tcp_hlen=(transport[12]>>4)*4;
        if(tcp_hlen<20||tcp_hlen>total-hlen)goto drop;
    } else {
        unsigned udp_len=((unsigned)transport[4]<<8)|transport[5];
        if(udp_len<8||udp_len>total-hlen)goto drop;
    }
    return packet;
drop:
    pbuf_free(packet);
    return NULL;
}

err_t __wrap_ip4_input(struct pbuf *packet, struct netif *input)
{
    LWIP_ASSERT_CORE_LOCKED();
    packet=prepare_dnat_packet(packet,input);
    if(!packet)return ERR_OK;
    if (!tailnet_forward_allow_ipv4_packet(packet, input)) {
        pbuf_free(packet);
        return ERR_OK;
    }
    return __real_ip4_input(packet, input);
}
