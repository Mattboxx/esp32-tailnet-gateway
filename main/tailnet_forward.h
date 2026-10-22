/* Dedicated uplink-LAN -> Tailnet service forwarding. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "lwip/pbuf.h"
#include "lwip/netif.h"

#define TAILNET_FORWARD_MAX 8
#define TAILNET_FORWARD_NAME_LEN 32
#define TAILNET_FORWARD_DEST_LEN 96
#define TAILNET_FORWARD_PROTO_TCP 6
#define TAILNET_FORWARD_PROTO_UDP 17

typedef struct {
    uint8_t valid, enabled, proto, source_prefix;
    uint16_t listen_port, destination_port;
    uint32_t source_network;
    char name[TAILNET_FORWARD_NAME_LEN];
    char destination[TAILNET_FORWARD_DEST_LEN];
    uint8_t _reserved[8];
} tailnet_forward_rule_t;

typedef struct {
    bool installed;
    uint32_t resolved_ip;
    uint32_t accepted_packets, blocked_packets;
    uint32_t last_accepted_s, last_blocked_s; /* uptime seconds, 0 = never this boot */
    char error[64];
} tailnet_forward_runtime_t;

/* Ephemeral snapshot, never written to NVS. Installation and packet policy
 * use the same copy even if a settings task publishes another configuration. */
typedef struct {
    tailnet_forward_rule_t rule;
    uint32_t destination_nbo, binding_ip_nbo;
    int slot;
    uint64_t generation;
} tailnet_forward_mapping_t;

void tailnet_forward_init(void);
int tailnet_forward_count(void);
bool tailnet_forward_get(int index, tailnet_forward_rule_t *rule, tailnet_forward_runtime_t *runtime);
esp_err_t tailnet_forward_set_all(const tailnet_forward_rule_t *rules, int count, char *error, size_t error_size);
esp_err_t tailnet_forward_set_enabled(int index, bool enabled);
esp_err_t tailnet_forward_set_enabled_bound(int index,uint32_t expected_rule,bool enabled);
#define TAILNET_TABLE_GUARD_LEN 34
typedef struct {char guard[TAILNET_TABLE_GUARD_LEN];int previous_count,previous_enabled;} tailnet_forward_preview_t;
/* Optimistic configuration selector, NOT authentication. Preview never saves. */
esp_err_t tailnet_forward_replace_guarded(const tailnet_forward_rule_t *rules,int count,const char *expected,bool apply,
                                         tailnet_forward_preview_t *preview,char *error,size_t error_size);
esp_err_t tailnet_forward_parse_cidr(const char *text, uint32_t *network_hbo, uint8_t *prefix);
void tailnet_forward_format_cidr(uint32_t network_hbo, uint8_t prefix, char *out, size_t out_size);
bool tailnet_forward_listen_conflicts(uint8_t proto, uint16_t port);
bool tailnet_forward_get_mapping(int slot, uint8_t *proto, uint16_t *listen_port, uint32_t *destination_nbo, uint16_t *destination_port);
int tailnet_forward_snapshot_mappings(tailnet_forward_mapping_t *out, int capacity);
void tailnet_forward_prepare_install(void);
void tailnet_forward_mark_installed(const tailnet_forward_mapping_t *mapping, bool installed, const char *error);
/* Called only at IPv4 input on the TCP/IP core, immediately before DNAT. */
bool tailnet_forward_allow_ipv4_packet(struct pbuf *packet, struct netif *input);
/* local_ip_nbo is the receiving interface's IPv4 address, not a route
 * destination. The SDK applies receive-side DNAT only to that address. */
bool tailnet_forward_allow_uplink_packet(struct pbuf *packet, uint32_t local_ip_nbo);
bool tailnet_forward_allow_non_uplink_packet(struct pbuf *packet, bool has_ethernet_header, uint32_t local_ip_nbo);
bool tailnet_forward_is_routed_target(uint8_t proto, uint32_t destination_nbo, uint16_t destination_port);
bool tailnet_forward_is_routed_response(uint8_t proto, uint32_t source_nbo, uint16_t source_port);
void tailnet_forward_totals(uint32_t *enabled, uint32_t *installed, uint32_t *accepted, uint32_t *blocked);
