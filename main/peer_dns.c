/* DNS-over-HTTP service for Tailscale peers using this node as an exit node.
 *
 * Native Tailscale clients send DNS wire messages to the PeerAPI address the
 * node advertises: http://<tailnet-ip>:<TAILSCALE_PEERAPI_PORT>/dns-query.
 * The service has its own small HTTP server and runs only while the router
 * offers itself as an exit node: the admin web server handles one request at
 * a time, and a page load on a client is dozens of lookups, so sharing it
 * would stall the UI. Connections are authorised from the accepted socket's
 * addresses before any byte is read, and again for every request.
 *
 * Since 3.0.7-beta.9 that server is a minimal HTTP/1.1 implementation of the
 * one endpoint (GET and POST /dns-query, keep-alive, Content-Length bodies)
 * instead of an esp_http_server instance: the framework's control and message
 * sockets and per-server structures took 2.5 KB of internal RAM and three of
 * the 31 lwIP sockets (measured on board A). Buffers, stack and task live in
 * SPIRAM; only the listening socket and one socket per connection remain.
 * Latency comes first: as many connections as before, kept open longer than
 * clients keep them, answers sent in one segment without Nagle delay.
 *
 * Lookups go to the uplink resolver (or the DNS forwarder's configured
 * upstream): UDP first, TCP when the answer is truncated.
 *
 * Ported from Csontikka/esp32-tailscale-subnet-router v0.1.31, including
 * the PeerAPI DNS contribution by 5queezer; adapted for this fork's lifecycle,
 * configurable admin port, diagnostics and existing privacy policy.
 * SPDX-License-Identifier: MIT
 */

#include "peer_dns.h"

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "dns_relay.h"
#include "sockaddr_ipv4.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "microlink.h"
#include "tailscale_config.h"

#define PEER_DNS_MAX_MESSAGE       4096U
#define PEER_DNS_MAX_B64           (((PEER_DNS_MAX_MESSAGE + 2U) / 3U) * 4U)
#define PEER_DNS_MAX_QUERY_STRING  (PEER_DNS_MAX_B64 + 32U)
#define PEER_DNS_TIMEOUT_US        (3000LL * 1000LL)
#define PEER_DNS_UDP_TIMEOUT_US    (1500LL * 1000LL)
/* One retransmission of the same query within that budget: a single lost
 * UDP answer costs ~0.6 s instead of failing over to TCP, which many home
 * routers do not serve. */
#define PEER_DNS_UDP_RETRY_US      (600LL * 1000LL)
#define PEER_DNS_CLIENTS           3          /* concurrent connections, LRU replaced (as the old server) */
#define PEER_DNS_HEAD_MAX          (PEER_DNS_MAX_QUERY_STRING + 512U)
#define PEER_DNS_BUF_MAX           (PEER_DNS_HEAD_MAX + PEER_DNS_MAX_MESSAGE)
/* Longer than clients keep idle connections (Go net/http: 90 s), so the
 * server never forces a new TCP handshake on a client that would reuse one. */
#define PEER_DNS_IDLE_US           (120LL * 1000LL * 1000LL)
#define PEER_DNS_REQUEST_US        (5LL * 1000LL * 1000LL)
#define PEER_DNS_SEND_TIMEOUT_S    5
#define PEER_DNS_BACKLOG           2
#define PEER_DNS_STACK             6144

static const char *TAG = "peer_dns";
static TaskHandle_t s_task;

bool peer_dns_is_running(void) { return s_task != NULL; }

typedef enum {
    UPSTREAM_OK = 0,
    UPSTREAM_TIMEOUT,
    UPSTREAM_ERROR,
    UPSTREAM_NO_MEMORY,
} upstream_result_t;

static bool advertises_exit_node(void)
{
    return tailscale_exit_server_active();
}

/* IPv4 or IPv4-mapped (see sockaddr_ipv4.h); native IPv6 remains outside
 * this IPv4 PeerAPI contract. */
static bool sockaddr_ipv4_host(const struct sockaddr_storage *address,
                               uint32_t *ipv4_host)
{
    uint32_t ipv4_network;
    if (!sockaddr_ipv4_nbo(address, &ipv4_network)) return false;
    *ipv4_host = ntohl(ipv4_network);
    return true;
}

/* Requests are accepted only on the tunnel address and only when the remote
 * address exactly matches a peer currently known to microlink.  Merely being
 * in 100.64.0.0/10 is insufficient, so AP/LAN requests cannot use
 * this unauthenticated endpoint. */
static bool peer_fd_allowed(int fd)
{
    if (!advertises_exit_node()) return false;

    microlink_t *ml = tailscale_get_microlink();
    if (!ml || !microlink_is_connected(ml)) return false;

    uint32_t own_ip = microlink_get_vpn_ip(ml); /* host byte order */
    if (own_ip == 0) return false;

    if (fd < 0) return false;

    struct sockaddr_storage local = {0};
    struct sockaddr_storage remote = {0};
    socklen_t local_len = sizeof(local);
    socklen_t remote_len = sizeof(remote);
    uint32_t local_ip;
    uint32_t remote_ip;
    if (getsockname(fd, (struct sockaddr *)&local, &local_len) != 0 ||
        getpeername(fd, (struct sockaddr *)&remote, &remote_len) != 0 ||
        !sockaddr_ipv4_host(&local, &local_ip) ||
        !sockaddr_ipv4_host(&remote, &remote_ip) ||
        local_ip != own_ip) {
        return false;
    }

    int count = microlink_get_peer_count(ml);
    for (int i = 0; i < count; i++) {
        microlink_peer_info_t peer;
        if (microlink_get_peer_info(ml, i, &peer) == ESP_OK &&
            peer.vpn_ip != 0 && peer.vpn_ip == remote_ip) {
            return true;
        }
    }
    return false;
}

static bool dns_query_valid(const uint8_t *message, size_t length)
{
    /* A DNS header is 12 bytes and a query must have QR clear. */
    return message && length >= 12 && length <= PEER_DNS_MAX_MESSAGE &&
           (message[2] & 0x80U) == 0;
}

static int base64url_value(unsigned char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '-') return 62;
    if (c == '_') return 63;
    return -1;
}

/* RFC 8484 GET uses unpadded base64url.  Reject non-canonical trailing bits
 * rather than silently accepting a second spelling of the same DNS packet. */
static bool decode_base64url(const char *encoded, size_t encoded_len,
                             uint8_t *decoded, size_t decoded_cap,
                             size_t *decoded_len)
{
    if (!encoded || encoded_len == 0 || encoded_len > PEER_DNS_MAX_B64 ||
        (encoded_len & 3U) == 1U) {
        return false;
    }

    uint32_t accumulator = 0;
    unsigned bits = 0;
    size_t out = 0;
    for (size_t i = 0; i < encoded_len; i++) {
        int value = base64url_value((unsigned char)encoded[i]);
        if (value < 0) return false; /* Padding is forbidden too. */
        accumulator = (accumulator << 6) | (uint32_t)value;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (out >= decoded_cap) return false;
            decoded[out++] = (uint8_t)(accumulator >> bits);
        }
    }
    if (bits != 0 && (accumulator & ((1U << bits) - 1U)) != 0) return false;
    *decoded_len = out;
    return true;
}

static bool resolver_is_local(uint32_t resolver_nbo)
{
    esp_netif_t *interfaces[] = {
        esp_netif_get_handle_from_ifkey("WIFI_STA_DEF"),
        esp_netif_get_handle_from_ifkey("WIFI_AP_DEF"),
    };
    for (size_t i = 0; i < sizeof(interfaces) / sizeof(interfaces[0]); i++) {
        if (!interfaces[i]) continue;
        esp_netif_ip_info_t info = {0};
        if (esp_netif_get_ip_info(interfaces[i], &info) == ESP_OK &&
            info.ip.addr != 0 && info.ip.addr == resolver_nbo) {
            return true;
        }
    }

    microlink_t *ml = tailscale_get_microlink();
    return ml && microlink_get_vpn_ip(ml) == ntohl(resolver_nbo);
}

static bool resolver_is_usable(uint32_t resolver_nbo)
{
    uint32_t host = ntohl(resolver_nbo);
    if (host == 0 || host == UINT32_MAX) return false;
    if ((host & 0xFF000000U) == 0x00000000U || /* this network */
        (host & 0xFF000000U) == 0x7F000000U || /* loopback */
        (host & 0xE0000000U) == 0xE0000000U) { /* multicast/reserved */
        return false;
    }
    return !resolver_is_local(resolver_nbo);
}

/* Use an explicit DNS-relay upstream first, otherwise the resolver currently
 * installed on the STA netif.  There is intentionally no public fallback:
 * an absent or unsafe resolver is a configuration error, not permission to
 * send DNS traffic somewhere the operator did not choose. */
static uint32_t select_resolver(void)
{
    uint32_t resolver = dns_relay_get_upstream();
    if (resolver == 0) {
        esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        esp_netif_dns_info_t info = {0};
        if (!sta || esp_netif_get_dns_info(sta, ESP_NETIF_DNS_MAIN, &info) != ESP_OK ||
            info.ip.type != ESP_IPADDR_TYPE_V4) {
            return 0;
        }
        resolver = info.ip.u_addr.ip4.addr;
    }
    return resolver_is_usable(resolver) ? resolver : 0;
}

static int wait_for_socket(int fd, bool write_ready, int64_t deadline_us)
{
    for (;;) {
        int64_t remaining = deadline_us - esp_timer_get_time();
        if (remaining <= 0) return 0;

        fd_set read_set;
        fd_set write_set;
        FD_ZERO(&read_set);
        FD_ZERO(&write_set);
        if (write_ready) FD_SET(fd, &write_set);
        else FD_SET(fd, &read_set);
        struct timeval timeout = {
            .tv_sec = (long)(remaining / 1000000LL),
            .tv_usec = (long)(remaining % 1000000LL),
        };
        int rc = select(fd + 1, write_ready ? NULL : &read_set,
                        write_ready ? &write_set : NULL, NULL, &timeout);
        if (rc < 0 && errno == EINTR) continue;
        return rc;
    }
}

static upstream_result_t socket_write_all(int fd, const uint8_t *data,
                                          size_t length, int64_t deadline_us)
{
    size_t sent = 0;
    while (sent < length) {
        int ready = wait_for_socket(fd, true, deadline_us);
        if (ready == 0) return UPSTREAM_TIMEOUT;
        if (ready < 0) return UPSTREAM_ERROR;
        ssize_t n = send(fd, data + sent, length - sent, 0);
        if (n > 0) {
            sent += (size_t)n;
        } else if (n < 0 && (errno == EINTR || errno == EAGAIN ||
                             errno == EWOULDBLOCK)) {
            continue;
        } else {
            return UPSTREAM_ERROR;
        }
    }
    return UPSTREAM_OK;
}

static upstream_result_t socket_read_all(int fd, uint8_t *data,
                                         size_t length, int64_t deadline_us)
{
    size_t received = 0;
    while (received < length) {
        int ready = wait_for_socket(fd, false, deadline_us);
        if (ready == 0) return UPSTREAM_TIMEOUT;
        if (ready < 0) return UPSTREAM_ERROR;
        ssize_t n = recv(fd, data + received, length - received, 0);
        if (n > 0) {
            received += (size_t)n;
        } else if (n < 0 && (errno == EINTR || errno == EAGAIN ||
                             errno == EWOULDBLOCK)) {
            continue;
        } else {
            return UPSTREAM_ERROR;
        }
    }
    return UPSTREAM_OK;
}

/* One UDP exchange with `server` (network byte order). A truncated answer is
 * reported as such so the caller can repeat the question over TCP. */
static upstream_result_t forward_dns_udp(uint32_t server, const uint8_t *query,
                                         size_t query_len, uint8_t **response,
                                         size_t *response_len, bool *truncated)
{
    *truncated = false;
    uint8_t *answer = malloc(PEER_DNS_MAX_MESSAGE);
    if (!answer) return UPSTREAM_NO_MEMORY;

    int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (fd < 0) {
        free(answer);
        return UPSTREAM_ERROR;
    }
    struct sockaddr_in to = {
        .sin_family = AF_INET,
        .sin_port = htons(53),
        .sin_addr.s_addr = server,
    };
    upstream_result_t result = UPSTREAM_OK;
    if (sendto(fd, query, query_len, 0, (struct sockaddr *)&to, sizeof(to)) != (ssize_t)query_len) {
        result = UPSTREAM_ERROR;
    }
    int64_t start = esp_timer_get_time();
    int64_t deadline = start + PEER_DNS_UDP_TIMEOUT_US;
    int64_t retry_at = start + PEER_DNS_UDP_RETRY_US;
    bool resent = false;
    ssize_t n = 0;
    while (result == UPSTREAM_OK) {
        int ready = wait_for_socket(fd, false, resent ? deadline : retry_at);
        if (ready == 0 && !resent) {
            resent = true;
            if (sendto(fd, query, query_len, 0, (struct sockaddr *)&to, sizeof(to)) != (ssize_t)query_len)
                result = UPSTREAM_ERROR;
            continue;
        }
        if (ready <= 0) {
            result = ready == 0 ? UPSTREAM_TIMEOUT : UPSTREAM_ERROR;
            break;
        }
        struct sockaddr_in from = {0};
        socklen_t from_len = sizeof(from);
        n = recvfrom(fd, answer, PEER_DNS_MAX_MESSAGE, 0,
                     (struct sockaddr *)&from, &from_len);
        if (n < 0) {
            result = UPSTREAM_ERROR;
            break;
        }
        /* Only the server we asked, answering this question. */
        if (from.sin_family == AF_INET && from.sin_addr.s_addr == server &&
            from.sin_port == htons(53) && n >= 12 &&
            answer[0] == query[0] && answer[1] == query[1] &&
            (answer[2] & 0x80U) != 0) {
            break;
        }
    }
    close(fd);
    if (result != UPSTREAM_OK) {
        free(answer);
        return result;
    }
    if (answer[2] & 0x02U) {   /* TC */
        *truncated = true;
        free(answer);
        return UPSTREAM_OK;
    }
    *response = answer;
    *response_len = (size_t)n;
    return UPSTREAM_OK;
}

static upstream_result_t forward_dns_tcp(const uint8_t *query, size_t query_len,
                                         uint8_t **response, size_t *response_len);

/* UDP to the resolver, TCP only for a truncated answer or when UDP got
 * nothing: one datagram each way is what almost every lookup needs, and a TCP
 * connection per question tripled the time a client waits. */
static upstream_result_t forward_dns(const uint8_t *query, size_t query_len,
                                     uint8_t **response, size_t *response_len)
{
    uint32_t resolver = select_resolver();
    if (resolver == 0) return UPSTREAM_ERROR;
    bool truncated = false;
    upstream_result_t result = forward_dns_udp(resolver, query, query_len,
                                               response, response_len, &truncated);
    if (result == UPSTREAM_OK && !truncated) return UPSTREAM_OK;
    if (result == UPSTREAM_NO_MEMORY) return result;
    return forward_dns_tcp(query, query_len, response, response_len);
}

static upstream_result_t forward_dns_tcp(const uint8_t *query, size_t query_len,
                                         uint8_t **response, size_t *response_len)
{
    uint32_t resolver = select_resolver();
    if (resolver == 0) return UPSTREAM_ERROR;

    uint8_t *answer = malloc(PEER_DNS_MAX_MESSAGE);
    if (!answer) return UPSTREAM_NO_MEMORY;

    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) {
        free(answer);
        return UPSTREAM_ERROR;
    }

    int old_flags = fcntl(fd, F_GETFL, 0);
    if (old_flags < 0 || fcntl(fd, F_SETFL, old_flags | O_NONBLOCK) != 0) {
        close(fd);
        free(answer);
        return UPSTREAM_ERROR;
    }

    struct sockaddr_in upstream = {
        .sin_family = AF_INET,
        .sin_port = htons(53),
        .sin_addr.s_addr = resolver,
    };
    int64_t deadline = esp_timer_get_time() + PEER_DNS_TIMEOUT_US;
    if (connect(fd, (struct sockaddr *)&upstream, sizeof(upstream)) != 0) {
        if (errno != EINPROGRESS && errno != EAGAIN && errno != EWOULDBLOCK) {
            close(fd);
            free(answer);
            return UPSTREAM_ERROR;
        }
        int ready = wait_for_socket(fd, true, deadline);
        if (ready <= 0) {
            close(fd);
            free(answer);
            return ready == 0 ? UPSTREAM_TIMEOUT : UPSTREAM_ERROR;
        }
        int socket_error = 0;
        socklen_t error_len = sizeof(socket_error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &socket_error, &error_len) != 0 ||
            socket_error != 0) {
            close(fd);
            free(answer);
            return socket_error == ETIMEDOUT ? UPSTREAM_TIMEOUT : UPSTREAM_ERROR;
        }
    }

    uint8_t length_prefix[2] = {
        (uint8_t)(query_len >> 8),
        (uint8_t)(query_len & 0xFFU),
    };
    upstream_result_t result = socket_write_all(fd, length_prefix,
                                                sizeof(length_prefix), deadline);
    if (result == UPSTREAM_OK) {
        result = socket_write_all(fd, query, query_len, deadline);
    }

    uint8_t response_prefix[2] = {0};
    if (result == UPSTREAM_OK) {
        result = socket_read_all(fd, response_prefix, sizeof(response_prefix), deadline);
    }
    size_t wire_len = ((size_t)response_prefix[0] << 8) | response_prefix[1];
    if (result == UPSTREAM_OK &&
        (wire_len < 12 || wire_len > PEER_DNS_MAX_MESSAGE)) {
        result = UPSTREAM_ERROR;
    }
    if (result == UPSTREAM_OK) {
        result = socket_read_all(fd, answer, wire_len, deadline);
    }
    close(fd);

    if (result == UPSTREAM_OK &&
        (answer[0] != query[0] || answer[1] != query[1] ||
         (answer[2] & 0x80U) == 0)) {
        result = UPSTREAM_ERROR;
    }
    if (result != UPSTREAM_OK) {
        free(answer);
        return result;
    }

    *response = answer;
    *response_len = wire_len;
    return UPSTREAM_OK;
}

/* One request parsed from the start of a connection buffer. Pure: tested on
 * the host with the actual code (tools/test_peer_dns.py). */
typedef enum {
    PEER_REQ_INCOMPLETE = 0,  /* need more bytes */
    PEER_REQ_GET,
    PEER_REQ_POST,
    PEER_REQ_BAD,             /* 400 */
    PEER_REQ_NOT_FOUND,       /* 404 */
    PEER_REQ_METHOD,          /* 405 */
    PEER_REQ_TOO_LARGE,       /* 431 */
    PEER_REQ_MEDIA,           /* 415 */
} peer_req_kind_t;

typedef struct {
    peer_req_kind_t kind;
    const char *query;        /* GET: after '?', not NUL-terminated */
    size_t query_len;
    const uint8_t *body;      /* POST */
    size_t body_len;
    size_t consumed;          /* bytes of this request, body included */
    bool close;               /* answer, then close the connection */
} peer_request_t;

static bool token_is(const char *s, size_t n, const char *word)
{
    return n == strlen(word) && strncasecmp(s, word, n) == 0;
}

/* RFC 8484 media type, parameters allowed after ';'. */
static bool media_is_dns_message(const char *v, size_t n)
{
    while (n && (*v == ' ' || *v == '\t')) { v++; n--; }
    size_t m = 0;
    while (m < n && v[m] != ';' && v[m] != ' ' && v[m] != '\t') m++;
    return token_is(v, m, "application/dns-message");
}

static bool connection_has_close(const char *v, size_t n)
{
    for (size_t i = 0; i < n;) {
        while (i < n && (v[i] == ' ' || v[i] == '\t' || v[i] == ',')) i++;
        size_t start = i;
        while (i < n && v[i] != ',' && v[i] != ' ' && v[i] != '\t') i++;
        if (token_is(v + start, i - start, "close")) return true;
    }
    return false;
}

static void parse_request(const uint8_t *buf, size_t len, peer_request_t *out)
{
    memset(out, 0, sizeof *out);
    out->close = true;
    size_t limit = len < PEER_DNS_HEAD_MAX ? len : PEER_DNS_HEAD_MAX;
    size_t end = 0;
    for (size_t i = 0; i + 3 < limit; i++) {
        if (buf[i] == '\r' && buf[i + 1] == '\n' && buf[i + 2] == '\r' && buf[i + 3] == '\n') { end = i; break; }
    }
    if (!end) {
        out->kind = len >= PEER_DNS_HEAD_MAX ? PEER_REQ_TOO_LARGE : PEER_REQ_INCOMPLETE;
        return;
    }
    const char *h = (const char *)buf;
    if (memchr(h, '\0', end)) { out->kind = PEER_REQ_BAD; return; }
    /* Request line: METHOD SP TARGET SP HTTP/1.x */
    const char *line_end = memchr(h, '\r', end);
    size_t line_len = line_end ? (size_t)(line_end - h) : end;
    const char *sp1 = memchr(h, ' ', line_len);
    if (!sp1) { out->kind = PEER_REQ_BAD; return; }
    const char *target = sp1 + 1;
    const char *sp2 = memchr(target, ' ', line_len - (size_t)(target - h));
    if (!sp2 || sp2 == target) { out->kind = PEER_REQ_BAD; return; }
    size_t method_len = (size_t)(sp1 - h), target_len = (size_t)(sp2 - target);
    const char *version = sp2 + 1;
    size_t version_len = line_len - (size_t)(version - h);
    bool http11 = version_len == 8 && !memcmp(version, "HTTP/1.1", 8);
    if (!http11 && !(version_len == 8 && !memcmp(version, "HTTP/1.0", 8))) { out->kind = PEER_REQ_BAD; return; }
    bool get = method_len == 3 && !memcmp(h, "GET", 3);
    bool post = method_len == 4 && !memcmp(h, "POST", 4);
    /* Headers. */
    bool have_length = false, dns_type = false, close = !http11;
    size_t content_length = 0;
    for (size_t pos = line_len + 2; pos < end;) {
        const char *l = h + pos;
        const char *e = memchr(l, '\r', end - pos);
        size_t n = e ? (size_t)(e - l) : end - pos;
        if (!n || l[0] == ' ' || l[0] == '\t') { out->kind = PEER_REQ_BAD; return; }   /* obs-fold */
        const char *colon = memchr(l, ':', n);
        if (!colon || colon == l) { out->kind = PEER_REQ_BAD; return; }
        size_t name_len = (size_t)(colon - l);
        const char *v = colon + 1;
        size_t vn = n - name_len - 1;
        while (vn && (*v == ' ' || *v == '\t')) { v++; vn--; }
        while (vn && (v[vn - 1] == ' ' || v[vn - 1] == '\t')) vn--;
        if (token_is(l, name_len, "Content-Length")) {
            if (have_length || !vn || vn > 5) { out->kind = PEER_REQ_BAD; return; }
            size_t value = 0;
            for (size_t i = 0; i < vn; i++) {
                if (v[i] < '0' || v[i] > '9') { out->kind = PEER_REQ_BAD; return; }
                value = value * 10 + (size_t)(v[i] - '0');
            }
            have_length = true; content_length = value;
        } else if (token_is(l, name_len, "Transfer-Encoding")) {
            out->kind = PEER_REQ_BAD; return;    /* bodies only with Content-Length */
        } else if (token_is(l, name_len, "Content-Type")) {
            dns_type = media_is_dns_message(v, vn);
        } else if (token_is(l, name_len, "Connection")) {
            if (connection_has_close(v, vn)) close = true;
        }
        pos += n + 2;
    }
    size_t head = end + 4;
    out->close = close;
    bool path = target_len >= 10 && !memcmp(target, "/dns-query", 10) && (target_len == 10 || target[10] == '?');
    if (!get && !post) { out->kind = PEER_REQ_METHOD; out->close = true; return; }
    if (!path) { out->kind = PEER_REQ_NOT_FOUND; out->close = true; return; }
    if (get) {
        if (have_length && content_length) { out->kind = PEER_REQ_BAD; out->close = true; return; }
        if (target_len <= 11) { out->kind = PEER_REQ_BAD; out->close = true; return; }
        out->query = target + 11;
        out->query_len = target_len - 11;
        out->consumed = head;
        out->kind = PEER_REQ_GET;
        return;
    }
    if (!dns_type) { out->kind = PEER_REQ_MEDIA; out->close = true; return; }
    if (!have_length || content_length < 12 || content_length > PEER_DNS_MAX_MESSAGE) {
        out->kind = PEER_REQ_BAD; out->close = true; return;
    }
    if (len < head + content_length) { out->kind = PEER_REQ_INCOMPLETE; return; }
    out->body = buf + head;
    out->body_len = content_length;
    out->consumed = head + content_length;
    out->kind = PEER_REQ_POST;
}

/* GET ?dns=<base64url>: exactly one dns parameter, decoded into `query`. */
static bool get_query(const char *qs, size_t qs_len, uint8_t *query, size_t *query_len)
{
    const char *encoded = NULL;
    size_t encoded_len = 0;
    for (size_t i = 0; i < qs_len;) {
        size_t j = i;
        while (j < qs_len && qs[j] != '&') j++;
        if (j - i >= 4 && !memcmp(qs + i, "dns=", 4)) {
            if (encoded) return false;   /* duplicate dns parameter */
            encoded = qs + i + 4;
            encoded_len = j - i - 4;
        }
        i = j + 1;
    }
    return encoded && decode_base64url(encoded, encoded_len, query, PEER_DNS_MAX_MESSAGE, query_len) &&
           dns_query_valid(query, *query_len);
}

#ifndef PEER_DNS_HOST_TEST
static bool send_all(int fd, const void *data, size_t len)
{
    const uint8_t *p = data;
    while (len) {
        int n = send(fd, p, len, 0);
        if (n <= 0) return false;
        p += n; len -= (size_t)n;
    }
    return true;
}

/* Header and body leave in one send: one TCP segment for a DNS answer, no
 * wait for an ACK between two small writes. */
static bool respond(int fd, const char *status, const char *type, const void *body, size_t len, bool close)
{
    enum { HEAD = 192 };
    uint8_t *out = malloc(HEAD + len);
    if (!out) return false;
    int n = snprintf((char *)out, HEAD,
                     "HTTP/1.1 %s\r\nContent-Type: %s\r\nCache-Control: no-store\r\nContent-Length: %u\r\n%s\r\n",
                     status, type, (unsigned)len, close ? "Connection: close\r\n" : "");
    bool ok = n > 0 && n < HEAD;
    if (ok && len) memcpy(out + n, body, len);
    ok = ok && send_all(fd, out, (size_t)n + len);
    free(out);
    return ok;
}

static bool respond_error(int fd, const char *status, const char *message)
{
    (void)respond(fd, status, "text/plain; charset=utf-8", message, strlen(message), true);
    return false;   /* errors always close: an unread body is discarded with it */
}

/* Answers one parsed request; false when the connection must be closed. */
static bool serve(int fd, const peer_request_t *r)
{
    switch (r->kind) {
    case PEER_REQ_BAD: return respond_error(fd, "400 Bad Request", "invalid request");
    case PEER_REQ_NOT_FOUND: return respond_error(fd, "404 Not Found", "not found");
    case PEER_REQ_METHOD: return respond_error(fd, "405 Method Not Allowed", "method not allowed");
    case PEER_REQ_TOO_LARGE: return respond_error(fd, "431 Request Header Fields Too Large", "request too large");
    case PEER_REQ_MEDIA:
        return respond_error(fd, "415 Unsupported Media Type", "Content-Type must be application/dns-message");
    default: break;
    }
    if (!peer_fd_allowed(fd)) return respond_error(fd, "403 Forbidden", "forbidden");
    uint8_t *query = NULL;
    size_t query_len = 0;
    if (r->kind == PEER_REQ_GET) {
        query = malloc(PEER_DNS_MAX_MESSAGE);
        if (!query) return respond_error(fd, "500 Internal Server Error", "out of memory");
        if (!get_query(r->query, r->query_len, query, &query_len)) {
            free(query);
            return respond_error(fd, "400 Bad Request", "invalid dns query");
        }
    } else if (!dns_query_valid(r->body, r->body_len)) {
        return respond_error(fd, "400 Bad Request", "invalid dns query");
    }
    uint8_t *answer = NULL;
    size_t answer_len = 0;
    upstream_result_t result = forward_dns(query ? query : r->body, query ? query_len : r->body_len,
                                           &answer, &answer_len);
    free(query);
    if (result == UPSTREAM_TIMEOUT) return respond_error(fd, "504 Gateway Timeout", "DNS upstream timed out");
    if (result == UPSTREAM_NO_MEMORY) return respond_error(fd, "500 Internal Server Error", "out of memory");
    if (result != UPSTREAM_OK) return respond_error(fd, "502 Bad Gateway", "DNS upstream failed");
    bool ok = respond(fd, "200 OK", "application/dns-message", answer, answer_len, r->close);
    free(answer);
    return ok && !r->close;
}

typedef struct { int fd; uint8_t *buf; size_t used; int64_t last_us, request_us; } peer_client_t;
static peer_client_t s_clients[PEER_DNS_CLIENTS];

static void client_close(peer_client_t *c)
{
    if (c->fd >= 0) close(c->fd);
    free(c->buf);
    *c = (peer_client_t){ .fd = -1 };
}

/* Reads what is available and answers every complete request in the buffer. */
static void client_read(peer_client_t *c)
{
    if (c->used >= PEER_DNS_BUF_MAX) { client_close(c); return; }
    int n = recv(c->fd, c->buf + c->used, PEER_DNS_BUF_MAX - c->used, MSG_DONTWAIT);
    if (n <= 0) {
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
        client_close(c);
        return;
    }
    int64_t now = esp_timer_get_time();
    if (!c->used) c->request_us = now;
    c->used += (size_t)n;
    c->last_us = now;
    for (;;) {
        peer_request_t r;
        parse_request(c->buf, c->used, &r);
        if (r.kind == PEER_REQ_INCOMPLETE) return;
        if (!serve(c->fd, &r) || r.consumed == 0) { client_close(c); return; }
        memmove(c->buf, c->buf + r.consumed, c->used - r.consumed);
        c->used -= r.consumed;
        c->request_us = esp_timer_get_time();
        if (!c->used) return;
    }
}

static void server_task(void *arg)
{
    int listen_fd = (int)(intptr_t)arg;
    for (int i = 0; i < PEER_DNS_CLIENTS; i++) s_clients[i] = (peer_client_t){ .fd = -1 };
    for (;;) {
        fd_set readable;
        FD_ZERO(&readable);
        FD_SET(listen_fd, &readable);
        int top = listen_fd;
        for (int i = 0; i < PEER_DNS_CLIENTS; i++) {
            if (s_clients[i].fd < 0) continue;
            FD_SET(s_clients[i].fd, &readable);
            if (s_clients[i].fd > top) top = s_clients[i].fd;
        }
        struct timeval tv = { .tv_sec = 1 };
        int ready = select(top + 1, &readable, NULL, NULL, &tv);
        int64_t now = esp_timer_get_time();
        if (ready > 0 && FD_ISSET(listen_fd, &readable)) {
            int fd = accept(listen_fd, NULL, NULL);
            if (fd >= 0 && !peer_fd_allowed(fd)) {   /* nothing is read from others */
                close(fd);
                fd = -1;
            }
            if (fd >= 0) {
                /* Least recently used connection makes room, as httpd's LRU purge did. */
                peer_client_t *slot = NULL;
                for (int i = 0; i < PEER_DNS_CLIENTS; i++) {
                    if (s_clients[i].fd < 0) { slot = &s_clients[i]; break; }
                    if (!slot || s_clients[i].last_us < slot->last_us) slot = &s_clients[i];
                }
                if (slot->fd >= 0) client_close(slot);
                uint8_t *buf = heap_caps_malloc(PEER_DNS_BUF_MAX, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
                if (!buf) {
                    close(fd);
                } else {
                    struct timeval send_timeout = { .tv_sec = PEER_DNS_SEND_TIMEOUT_S };
                    (void)setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &send_timeout, sizeof send_timeout);
                    int nodelay = 1;   /* answers go out at once, never held by Nagle */
                    (void)setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof nodelay);
                    *slot = (peer_client_t){ .fd = fd, .buf = buf, .last_us = now, .request_us = now };
                }
            }
        }
        for (int i = 0; i < PEER_DNS_CLIENTS; i++) {
            peer_client_t *c = &s_clients[i];
            if (c->fd < 0) continue;
            if (ready > 0 && FD_ISSET(c->fd, &readable)) client_read(c);
            if (c->fd < 0) continue;
            /* Idle keep-alive and slow partial requests are closed. */
            if (now - c->last_us > PEER_DNS_IDLE_US || (c->used && now - c->request_us > PEER_DNS_REQUEST_US))
                client_close(c);
        }
    }
}

static int32_t s_start_internal_bytes, s_start_sockets;
int32_t peer_dns_start_internal_bytes(void) { return s_start_internal_bytes; }
int32_t peer_dns_start_sockets(void) { return s_start_sockets; }

static int count_sockets(void)
{
    int used = 0;
    for (int i = 0; i < CONFIG_LWIP_MAX_SOCKETS; i++) {
        int type; socklen_t size = sizeof type;
        if (getsockopt(LWIP_SOCKET_OFFSET + i, SOL_SOCKET, SO_TYPE, &type, &size) == 0) used++;
    }
    return used;
}

void peer_dns_start(void)
{
    if (s_task || !tailscale_exit_server_active()) return;
    size_t free_before = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    int sockets_before = count_sockets();
    uint16_t port = tailscale_peerapi_port();
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) {
        ESP_LOGE(TAG, "exit-node DNS service: no socket (%d)", errno);
        return;
    }
    int one = 1;
    (void)setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in local = { .sin_family = AF_INET, .sin_port = htons(port), .sin_addr.s_addr = htonl(INADDR_ANY) };
    if (bind(fd, (struct sockaddr *)&local, sizeof local) != 0 || listen(fd, PEER_DNS_BACKLOG) != 0) {
        ESP_LOGE(TAG, "exit-node DNS service failed to listen on port %u (%d)", (unsigned)port, errno);
        close(fd);
        return;
    }
    TaskHandle_t task = NULL;
    /* SPIRAM stack and TCB: internal RAM is the scarce pool on this board. */
    if (xTaskCreateWithCaps(server_task, "peer_dns", PEER_DNS_STACK, (void *)(intptr_t)fd, 5, &task,
                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) != pdPASS) {
        ESP_LOGE(TAG, "exit-node DNS service: task not started");
        close(fd);
        return;
    }
    s_task = task;
    /* Approximate: other tasks allocate meanwhile; measured once per start. */
    s_start_internal_bytes = (int32_t)free_before - (int32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    s_start_sockets = count_sockets() - sockets_before;
    ESP_LOGW(TAG, "exit-node DNS service on port %u", (unsigned)port);
}
#endif /* PEER_DNS_HOST_TEST */
