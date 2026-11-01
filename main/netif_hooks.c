/* lwIP netif hook installer — ACL packet filter.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stddef.h>
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#include "lwip/err.h"
#include "lwip/tcpip.h"
#include "netif/ethernet.h"
#include "web_ui.h"
#include "first_boot.h"

#include <string.h>
#include "lwip/ip4.h"
#include "lwip/inet_chksum.h"
#include "lwip/prot/ip.h"
#include "lwip/prot/tcp.h"

#include "acl.h"
#include "netif_hooks.h"
#include "tailnet_forward.h"

/* MTU-management knobs published by tailscale_mtu.c. ap_mss_clamp is
 * the cap we enforce on every TCP SYN crossing the AP interface (so
 * neither side proposes a segment bigger than the tunnel can carry).
 * ap_pmtu is the next-hop MTU we report back when a DF=1 packet
 * arrives oversized — implements RFC 1191 Path MTU Discovery from
 * the AP side. 0 = feature disabled. */
extern uint16_t ap_mss_clamp;
extern uint16_t ap_pmtu;

static const char *TAG = "netif_hooks";

/* Original lwIP function pointers — captured before we install our
 * shim and called from inside it so packets that pass the ACL still
 * reach the rest of the stack unmodified. */
static netif_input_fn       original_sta_input       = NULL;
static netif_linkoutput_fn  original_sta_linkoutput  = NULL;
static netif_input_fn       original_ap_input        = NULL;
static netif_linkoutput_fn  original_ap_linkoutput   = NULL;
/* Optional SPI Ethernet uplink: the same ESP-bound ACL chains as the STA. */
static netif_input_fn       original_eth_input       = NULL;
static netif_linkoutput_fn  original_eth_linkoutput  = NULL;
static bool                 s_eth_protected          = false;
static netif_output_fn      original_ppp_output      = NULL;
static struct netif        *s_ppp                    = NULL;
static volatile uint64_t    s_ppp_bytes_in           = 0;
static volatile uint64_t    s_ppp_bytes_out          = 0;

/* Wire-byte counters. Updated on the LWIP TCPIP task, read from the
 * HTTP server task. Display-only — torn reads at the 32-bit boundary
 * are tolerable for a UI gauge. */
static volatile uint64_t s_sta_bytes_in  = 0;
static volatile uint64_t s_sta_bytes_out = 0;
static volatile uint64_t s_ap_bytes_in   = 0;
static volatile uint64_t s_ap_bytes_out  = 0;

uint64_t netif_hooks_get_sta_bytes_in (void) { return s_sta_bytes_in;  }
uint64_t netif_hooks_get_sta_bytes_out(void) { return s_sta_bytes_out; }
uint64_t netif_hooks_get_ap_bytes_in  (void) { return s_ap_bytes_in;   }
uint64_t netif_hooks_get_ap_bytes_out (void) { return s_ap_bytes_out;  }

/* Saturation counters for the STA path: frames the next stage refused after
 * the ACL let them through (input: TCP/IP mailbox full or no memory; output:
 * Wi-Fi driver without TX buffers). The refusing caller frees the frame;
 * these only count. Single writer each; read for /api/operations. */
static volatile uint32_t s_sta_input_refused  = 0;
static volatile uint32_t s_sta_output_refused = 0;

uint32_t netif_hooks_get_sta_input_refused (void) { return s_sta_input_refused;  }
uint32_t netif_hooks_get_sta_output_refused(void) { return s_sta_output_refused; }

/* Overload shedding on the STA input path (3.0.7). STA frames posted to the
 * TCPIP thread and not yet handled are counted. Once STA_SHED_FROM of the
 * CONFIG_LWIP_TCPIP_RECVMBOX_SIZE mailbox slots are taken, bulk frames are
 * dropped:
 *   - IPv4 not addressed to the gateway (routed/NAT forwarding);
 *   - TCP to the gateway's own service ports (Service Gateway, port maps).
 * The remaining slots stay free for what the gateway itself must receive:
 *   - ARP, broadcast and multicast;
 *   - ICMP and UDP to its address (WireGuard/DISCO, DNS, DHCP, SNMP);
 *   - TCP to the web UI port and to its own client connections (ephemeral
 *     ports: control plane, DERP, MQTT, ntfy).
 * TCP retransmits the dropped bulk segments. Without this, the full mailbox
 * dropped any frame, including web UI requests and the WireGuard packets
 * that carry the returning TCP ACKs (3.0.7-dev.10/11 measurements). IPv6 and
 * anything not parsed is never shed. */
/* Bulk frames may fill at most 24 slots, fewer than the 32-entry mailbox of
 * 3.0.6, so queueing delay under load does not grow with the larger
 * mailbox; the other 40 slots are reserved for priority frames. */
#define STA_SHED_FROM 24
#define STA_EPHEMERAL_FIRST 0xC000u
static volatile uint32_t s_sta_queued;
static volatile uint32_t s_sta_input_shed;

uint32_t netif_hooks_get_sta_input_shed(void) { return s_sta_input_shed; }

/* own_ip: the STA address in network byte order; web_port: 0 if none. */
bool netif_hooks_sta_frame_priority(const struct pbuf *p, uint32_t own_ip, uint16_t web_port)
{
    if (!p || p->len < 14) return true;
    const uint8_t *f = (const uint8_t *)p->payload;
    uint16_t type = (uint16_t)((f[12] << 8) | f[13]);
    if (type != 0x0800) return true;                 /* ARP, IPv6, VLAN, ...: never shed */
    if (p->len < 14 + 20) return true;
    const uint8_t *ip = f + 14;
    unsigned ihl = (ip[0] & 0x0fu) * 4u;
    if ((ip[0] >> 4) != 4 || ihl < 20) return true;
    if (ip[16] == 255 || (ip[16] & 0xf0u) == 0xe0u) return true;   /* broadcast/multicast */
    uint32_t dst;
    memcpy(&dst, ip + 16, 4);
    if (dst != own_ip) return false;                 /* forwarded */
    uint8_t proto = ip[9];
    if (proto != 6) return true;                     /* ICMP, UDP, others to the gateway */
    if (((ip[6] & 0x1fu) | ip[7]) || p->len < 14 + ihl + 4) return true;  /* fragment/short */
    uint16_t dport = (uint16_t)((ip[ihl + 2] << 8) | ip[ihl + 3]);
    return dport == web_port || dport >= STA_EPHEMERAL_FIRST;
}

/* Runs in the TCPIP thread for every counted STA frame. */
static err_t sta_ethernet_input_counted(struct pbuf *p, struct netif *netif)
{
    __atomic_fetch_sub(&s_sta_queued, 1, __ATOMIC_RELAXED);
    return ethernet_input(p, netif);
}

/* TTL override (0 = pass through). Read on every STA-out packet, set
 * by the /api/network POST handler + the boot-time NVS load. Single
 * byte → atomic on Xtensa, no lock needed. */
static volatile uint8_t s_sta_ttl_override = 0;
void    netif_hooks_set_sta_ttl(uint8_t ttl) { s_sta_ttl_override = ttl; }
uint8_t netif_hooks_get_sta_ttl(void)        { return s_sta_ttl_override; }

/* Clamp the TCP MSS option in a SYN packet to max_mss. Operates on raw
 * Ethernet frames (14-byte header + IPv4 + TCP). Updates the TCP
 * checksum incrementally per RFC 1624. Pbuf must carry the whole TCP
 * header + options in its first segment; lwIP allocates those
 * contiguously for incoming packets so this is always the case in
 * practice. No-op on every other shape (UDP, IPv6, runts, non-SYN). */
static void clamp_tcp_mss(struct pbuf *p, uint16_t max_mss)
{
    if (max_mss == 0 || p == NULL) return;
    if (p->len < 14 + 20 + 20) return;
    uint8_t *payload = (uint8_t *)p->payload;
    if (payload[12] != 0x08 || payload[13] != 0x00) return;        /* IPv4? */
    struct ip_hdr *iphdr = (struct ip_hdr *)(payload + 14);
    if (IPH_V(iphdr) != 4 || IPH_PROTO(iphdr) != IP_PROTO_TCP) return;
    uint16_t ip_hdr_len = IPH_HL(iphdr) * 4;
    if (p->len < 14 + ip_hdr_len + 20) return;
    uint8_t *tcphdr = payload + 14 + ip_hdr_len;
    /* SYN bit: TCP flags byte at offset 13, SYN = bit 1. */
    if (!(tcphdr[13] & 0x02)) return;
    uint8_t tcp_hdr_len = (tcphdr[12] >> 4) * 4;
    if (tcp_hdr_len < 20 || p->len < 14 + ip_hdr_len + tcp_hdr_len) return;

    /* Walk the TCP options TLV. MSS option is kind=2, len=4, payload
     * is 16-bit MSS in network order. */
    uint8_t *opt     = tcphdr + 20;
    uint8_t *opt_end = tcphdr + tcp_hdr_len;
    while (opt < opt_end) {
        uint8_t kind = opt[0];
        if (kind == 0) break;                  /* end-of-list */
        if (kind == 1) { opt++; continue; }    /* NOP */
        if (opt + 1 >= opt_end) break;
        uint8_t opt_len = opt[1];
        if (opt_len < 2 || opt + opt_len > opt_end) break;
        if (kind == 2 && opt_len == 4) {
            uint16_t *mss_ptr = (uint16_t *)(opt + 2);
            if (lwip_ntohs(*mss_ptr) > max_mss) {
                uint16_t old_mss_net = *mss_ptr;
                *mss_ptr = lwip_htons(max_mss);
                /* RFC 1624 incremental: HC' = ~(~HC + ~m + m'). */
                uint16_t *chksum = (uint16_t *)(tcphdr + 16);
                uint32_t sum = (uint16_t)~(*chksum);
                sum += (uint16_t)~old_mss_net;
                sum += lwip_htons(max_mss);
                while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
                *chksum = (uint16_t)~sum;
            }
            break;
        }
        opt += opt_len;
    }
}

/* Send an ICMP "Fragmentation Needed and DF set" (RFC 1191 type 3 /
 * code 4) back to an AP client. Triggered when the client sends a
 * DF=1 frame bigger than `mtu`. Source IP comes from the netif so
 * we don't need a separate cached global. */
static void send_icmp_frag_needed(struct pbuf *p, struct netif *netif, uint16_t mtu)
{
    if (p == NULL || netif == NULL || original_ap_linkoutput == NULL) return;
    if (p->len < 14 + 20) return;
    uint8_t *eth = (uint8_t *)p->payload;
    if (eth[12] != 0x08 || eth[13] != 0x00) return;                /* IPv4 only */
    struct ip_hdr *orig_ip = (struct ip_hdr *)(eth + 14);
    if (IPH_V(orig_ip) != 4) return;
    uint16_t ip_total_len = lwip_ntohs(IPH_LEN(orig_ip));
    if (ip_total_len <= mtu) return;

    uint16_t flags_offset = lwip_ntohs(IPH_OFFSET(orig_ip));
    if (!(flags_offset & IP_DF)) return;                           /* DF not set */
    if (flags_offset & IP_OFFMASK) return;                         /* later fragment */
    if (IPH_PROTO(orig_ip) == IP_PROTO_ICMP) return;               /* no feedback loops */

    uint16_t orig_ihl = IPH_HL(orig_ip) * 4;
    if (orig_ihl < 20 || orig_ihl > 60) return;

    /* RFC 1191 reply body: 4 bytes (unused16 + nexthop-mtu16) + the
     * triggering IP header + first 8 bytes of payload. */
    uint16_t avail_data = (p->len > 14u + orig_ihl) ? (p->len - 14u - orig_ihl) : 0;
    if (avail_data > 8) avail_data = 8;
    uint16_t icmp_body  = 4 + orig_ihl + avail_data;
    uint16_t icmp_total = 4 + icmp_body;
    uint16_t new_ip_len = 20 + icmp_total;
    uint16_t frame_len  = 14 + new_ip_len;

    struct pbuf *resp = pbuf_alloc(PBUF_RAW, frame_len, PBUF_RAM);
    if (!resp) return;
    uint8_t *buf = (uint8_t *)resp->payload;
    memset(buf, 0, frame_len);

    /* Ethernet — swap MACs so the reply heads back to the client. */
    memcpy(buf + 0, eth + 6, 6);
    memcpy(buf + 6, eth + 0, 6);
    buf[12] = 0x08; buf[13] = 0x00;

    /* IPv4 header. */
    struct ip_hdr *rip = (struct ip_hdr *)(buf + 14);
    IPH_VHL_SET(rip, 4, 5);
    IPH_TOS_SET(rip, 0);
    IPH_LEN_SET(rip, lwip_htons(new_ip_len));
    IPH_ID_SET(rip, 0);
    IPH_OFFSET_SET(rip, 0);
    IPH_TTL_SET(rip, 64);
    IPH_PROTO_SET(rip, IP_PROTO_ICMP);
    IPH_CHKSUM_SET(rip, 0);
    rip->src.addr  = netif->ip_addr.u_addr.ip4.addr;
    rip->dest.addr = orig_ip->src.addr;
    IPH_CHKSUM_SET(rip, inet_chksum(rip, 20));

    /* ICMP destination-unreachable / fragmentation-needed. */
    uint8_t *icmp = buf + 14 + 20;
    icmp[0] = 3;                       /* type: destination unreachable */
    icmp[1] = 4;                       /* code: frag-needed, DF set     */
    icmp[2] = 0; icmp[3] = 0;          /* checksum (filled below)        */
    icmp[4] = 0; icmp[5] = 0;          /* reserved (RFC 1191 unused)     */
    icmp[6] = (uint8_t)(mtu >> 8);
    icmp[7] = (uint8_t)(mtu & 0xff);
    memcpy(icmp + 8, orig_ip, orig_ihl);
    if (avail_data > 0) {
        memcpy(icmp + 8 + orig_ihl, (uint8_t *)orig_ip + orig_ihl, avail_data);
    }
    *((uint16_t *)(icmp + 2)) = inet_chksum(icmp, icmp_total);

    original_ap_linkoutput(netif, resp);
    pbuf_free(resp);
}

/* Rewrite the IPv4 TTL field of an outgoing STA frame in place and patch
 * the header checksum (RFC 1624 incremental update). Pbuf must be at
 * least eth-header + ip-header big and carry IPv4. No-op on every other
 * shape — IPv6, ARP, runt frames pass through untouched. */
static inline void apply_sta_ttl_override(struct pbuf *p)
{
    uint8_t override = s_sta_ttl_override;
    if (override == 0 || !p) return;
    if (p->len < 14 + (int)sizeof(struct ip_hdr)) return;
    uint8_t *payload = (uint8_t *)p->payload;
    /* Ethertype IPv4? */
    if (payload[12] != 0x08 || payload[13] != 0x00) return;
    struct ip_hdr *iphdr = (struct ip_hdr *)(payload + 14);
    if (IPH_V(iphdr) != 4) return;
    if (iphdr->_ttl == override) return; /* already at target — skip checksum recompute */

    /* RFC 1624: HC' = ~(~HC + ~m + m'), where m and m' span the same
     * 16-bit word as the TTL byte. _ttl is the high byte of that word
     * (protocol field is the low byte), so we read the word, rewrite
     * the high byte, and incrementally update the checksum. */
    uint16_t old_word = *(uint16_t *)&iphdr->_ttl;
    iphdr->_ttl = override;
    uint16_t new_word = *(uint16_t *)&iphdr->_ttl;
    uint32_t sum = (uint16_t)~iphdr->_chksum;
    sum += (uint16_t)~old_word;
    sum += new_word;
    while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
    iphdr->_chksum = (uint16_t)~sum;
}

/* ACL check. (A PCAP tap used to live here; the capture feature was
 * removed.) Thin wrapper so the hook call sites stay unchanged. */
static inline uint8_t acl_check_and_tap(uint8_t list_id, struct pbuf *p, bool is_ap)
{
    (void)is_ap;
    return acl_check_packet(list_id, p);
}

static inline bool acl_drops(uint8_t action)
{
    return (action != ACL_NO_MATCH) && ((action & 0x01) == ACL_DENY);
}

static err_t sta_input_hook(struct pbuf *p, struct netif *netif)
{
    if (p) s_sta_bytes_in += p->tot_len;
    if (acl_drops(acl_check_and_tap(ACL_TO_ESP, p, false))) { pbuf_free(p); return ERR_OK; }
    if (!original_sta_input) return ERR_VAL;
    err_t err;
    if (original_sta_input == tcpip_input && (netif->flags & (NETIF_FLAG_ETHARP | NETIF_FLAG_ETHERNET))) {
        /* Same delivery as tcpip_input() for an Ethernet netif, counted. */
        uint32_t queued = __atomic_fetch_add(&s_sta_queued, 1, __ATOMIC_RELAXED);
        if (queued >= STA_SHED_FROM &&
            !netif_hooks_sta_frame_priority(p, ip4_addr_get_u32(netif_ip4_addr(netif)), web_ui_active_port())) {
            __atomic_fetch_sub(&s_sta_queued, 1, __ATOMIC_RELAXED);
            s_sta_input_shed++;
            pbuf_free(p);
            return ERR_OK;
        }
        err = tcpip_inpkt(p, netif, sta_ethernet_input_counted);
        if (err != ERR_OK) __atomic_fetch_sub(&s_sta_queued, 1, __ATOMIC_RELAXED);
    } else {
        err = original_sta_input(p, netif);
    }
    if (err != ERR_OK) s_sta_input_refused++;
    return err;
}

static err_t sta_linkoutput_hook(struct netif *netif, struct pbuf *p)
{
    if (p) s_sta_bytes_out += p->tot_len;
    /* TTL rewrite happens BEFORE the ACL check so the ACL rules see
     * the value that actually goes out the wire. */
    apply_sta_ttl_override(p);
    if (acl_drops(acl_check_and_tap(ACL_FROM_ESP, p, false))) { return ERR_OK; }
    if (!original_sta_linkoutput) return ERR_VAL;
    err_t err = original_sta_linkoutput(netif, p);
    if (err != ERR_OK) s_sta_output_refused++;
    return err;
}

static err_t eth_input_hook(struct pbuf *p, struct netif *netif)
{
    if (acl_drops(acl_check_and_tap(ACL_TO_ESP, p, false))) { pbuf_free(p); return ERR_OK; }
    return original_eth_input ? original_eth_input(p, netif) : ERR_VAL;
}

static err_t eth_linkoutput_hook(struct netif *netif, struct pbuf *p)
{
    if (acl_drops(acl_check_and_tap(ACL_FROM_ESP, p, false))) { return ERR_OK; }
    return original_eth_linkoutput ? original_eth_linkoutput(netif, p) : ERR_VAL;
}

bool netif_hooks_eth_protected(void) { return s_eth_protected; }

/* PPP: raw IPv4, so the explicit IP parser, never the Ethernet guess. */
static err_t ppp_output_hook(struct netif *netif, struct pbuf *p, const ip4_addr_t *ipaddr)
{
    if (p) s_ppp_bytes_out += p->tot_len;
    if (acl_drops(acl_check_ip_packet(ACL_FROM_ESP, p))) { return ERR_OK; }
    return original_ppp_output ? original_ppp_output(netif, p, ipaddr) : ERR_VAL;
}

bool netif_hooks_install_ppp(struct netif *nif)
{
    if (s_ppp) return s_ppp == nif;
    if (!nif || !nif->output) return false;
    original_ppp_output = nif->output;
    nif->output = ppp_output_hook;
    s_ppp = nif;
    ESP_LOGI(TAG, "PPP ACL hooks installed on %c%c%d", nif->name[0], nif->name[1], nif->num);
    return true;
}

bool netif_hooks_ppp_input_allowed(struct pbuf *p, struct netif *input)
{
    if (!s_ppp || input != s_ppp || !p) return true;
    s_ppp_bytes_in += p->tot_len;
    return !acl_drops(acl_check_ip_packet(ACL_TO_ESP, p));
}

uint64_t netif_hooks_get_ppp_bytes_in (void) { return s_ppp_bytes_in;  }
uint64_t netif_hooks_get_ppp_bytes_out(void) { return s_ppp_bytes_out; }

static err_t ap_input_hook(struct pbuf *p, struct netif *netif)
{
    if (p) s_ap_bytes_in += p->tot_len;
    /* Open first-boot AP: clients may reach only the gateway itself, never
     * the uplink LAN tested by the wizard. Headers are in the first pbuf. */
    if (p && !first_boot_ap_frame_allowed((const uint8_t *)p->payload, p->len)) { pbuf_free(p); return ERR_OK; }
    if (acl_drops(acl_check_and_tap(ACL_TO_AP, p, true))) { pbuf_free(p); return ERR_OK; }
    /* PMTU: tell the client to back off when it sends a DF packet
     * bigger than the tunnel can carry. Runs BEFORE we forward so the
     * client gets the signal even when we'd otherwise drop the frame. */
    if (ap_pmtu > 0) send_icmp_frag_needed(p, netif, ap_pmtu);
    /* MSS-clamp on TCP SYNs from the client side so neither end of the
     * connection proposes a segment bigger than the tunnel allows. */
    clamp_tcp_mss(p, ap_mss_clamp);
    return original_ap_input ? original_ap_input(p, netif) : ERR_VAL;
}

static err_t ap_linkoutput_hook(struct netif *netif, struct pbuf *p)
{
    if (p) s_ap_bytes_out += p->tot_len;
    if (acl_drops(acl_check_and_tap(ACL_FROM_AP, p, true))) { return ERR_OK; }
    /* And clamp again on outbound — SYN-ACK from upstream toward the
     * client also needs its MSS bounded. */
    clamp_tcp_mss(p, ap_mss_clamp);
    return original_ap_linkoutput ? original_ap_linkoutput(netif, p) : ERR_VAL;
}

void netif_hooks_refresh(void)
{
    /* Compatibility entry point for the forwarding manager. Tailnet policy
     * lives in __wrap_ip4_input, so no tunnel netif shim is needed here.
     * Reinstalling a transparent shim over SNMP's periodic traffic shim
     * captures the two wrappers as each other's "original", forming a
     * recursive input chain. SNMP alone owns the tunnel's input wrapper.
     * Physical STA/AP ACL hooks are installed once, before SNMP starts. */
}


void netif_hooks_init(void)
{
    static bool installed = false;
    if (installed) return;

    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_t *ap  = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");

    if (sta) {
        struct netif *nif = esp_netif_get_netif_impl(sta);
        if (nif) {
            original_sta_input      = nif->input;
            original_sta_linkoutput = nif->linkoutput;
            nif->input              = sta_input_hook;
            nif->linkoutput         = sta_linkoutput_hook;
            ESP_LOGI(TAG, "STA hooks installed on %c%c%d", nif->name[0], nif->name[1], nif->num);
        }
    }
    if (ap) {
        struct netif *nif = esp_netif_get_netif_impl(ap);
        if (nif) {
            original_ap_input       = nif->input;
            original_ap_linkoutput  = nif->linkoutput;
            nif->input              = ap_input_hook;
            nif->linkoutput         = ap_linkoutput_hook;
            ESP_LOGI(TAG, "AP hooks installed on %c%c%d", nif->name[0], nif->name[1], nif->num);
        }
    }

    /* Exists only when the optional Ethernet uplink was prepared at boot;
     * it is started afterwards, never before these hooks are in place. */
    esp_netif_t *eth = esp_netif_get_handle_from_ifkey("ETH_DEF");
    if (eth) {
        struct netif *nif = esp_netif_get_netif_impl(eth);
        if (nif && nif->input && nif->linkoutput) {
            original_eth_input      = nif->input;
            original_eth_linkoutput = nif->linkoutput;
            nif->input              = eth_input_hook;
            nif->linkoutput         = eth_linkoutput_hook;
            s_eth_protected         = true;
            ESP_LOGI(TAG, "Ethernet ACL hooks installed on %c%c%d", nif->name[0], nif->name[1], nif->num);
        }
    }

    installed = (sta != NULL) || (ap != NULL);
    netif_hooks_refresh();
}
