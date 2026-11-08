/* Web UI session admission without closing waiting requests.
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * The HTTP server used to close its least-recently-used session to admit a
 * new connection (lru_purge). The session it picked was usually one accepted
 * a moment earlier whose request bytes had not arrived yet, so the client
 * saw a reset: PERF-09 on 3.0.7-beta.2 recorded connection resets after
 * 0.2-0.5 s in bursts of 16 parallel status reads (3.0.6 behaved the same).
 *
 * Now the server keeps its slots and new connections wait in the listen
 * backlog. Sessions with no traffic in either direction for WEB_IDLE_CLOSE_MS
 * are closed, so idle keep-alive connections cannot hold every slot. A UI
 * polling once a second is never idle that long. The sweep runs as httpd
 * work, so it never runs while a handler does. */
#include "web_idle.h"

#include <errno.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "lwip/sockets.h"

static const char *TAG = "web_idle";

typedef struct { int fd; int64_t last_us; } web_idle_slot_t;
static web_idle_slot_t s_slots[WEB_IDLE_SLOTS];
static esp_timer_handle_t s_timer;
static httpd_handle_t s_server;
static uint32_t s_closed;

static web_idle_slot_t *slot_find(int fd)
{
    for (int i = 0; i < WEB_IDLE_SLOTS; i++)
        if (s_slots[i].fd == fd) return &s_slots[i];
    return NULL;
}

/* Records activity on fd; the oldest entry makes room if the table is full. */
void web_idle_touch(int fd, int64_t now_us)
{
    web_idle_slot_t *s = slot_find(fd);
    if (!s) s = slot_find(-1);
    if (!s) {
        s = &s_slots[0];
        for (int i = 1; i < WEB_IDLE_SLOTS; i++)
            if (s_slots[i].last_us < s->last_us) s = &s_slots[i];
    }
    s->fd = fd;
    s->last_us = now_us;
}

/* Socket error codes as the server's default send/recv report them. */
static int sock_err(void)
{
    switch (errno) {
    case EAGAIN:
    case EINTR:  return HTTPD_SOCK_ERR_TIMEOUT;
    case EINVAL:
    case EBADF:
    case EFAULT:
    case ENOTSOCK: return HTTPD_SOCK_ERR_INVALID;
    default:     return HTTPD_SOCK_ERR_FAIL;
    }
}

static int idle_send(httpd_handle_t hd, int fd, const char *buf, size_t len, int flags)
{
    (void)hd;
    if (!buf) return HTTPD_SOCK_ERR_INVALID;
    int ret = send(fd, buf, len, flags);
    if (ret < 0) return sock_err();
    web_idle_touch(fd, esp_timer_get_time());
    return ret;
}

static int idle_recv(httpd_handle_t hd, int fd, char *buf, size_t len, int flags)
{
    (void)hd;
    if (!buf) return HTTPD_SOCK_ERR_INVALID;
    int ret = recv(fd, buf, len, flags);
    if (ret < 0) return sock_err();
    web_idle_touch(fd, esp_timer_get_time());
    return ret;
}

esp_err_t web_idle_open(httpd_handle_t hd, int fd)
{
    web_idle_touch(fd, esp_timer_get_time());
    httpd_sess_set_send_override(hd, fd, idle_send);
    httpd_sess_set_recv_override(hd, fd, idle_recv);
    return ESP_OK;
}

/* Closes the sessions in fds[0..n) idle for WEB_IDLE_CLOSE_MS and forgets
 * entries for sockets that are gone. Returns the number of closures asked. */
int web_idle_sweep_fds(httpd_handle_t hd, const int *fds, size_t n, int64_t now_us)
{
    int closed = 0;
    for (int i = 0; i < WEB_IDLE_SLOTS; i++) {
        bool live = false;
        for (size_t j = 0; j < n; j++) live |= s_slots[i].fd == fds[j];
        if (!live) s_slots[i].fd = -1;
    }
    for (size_t j = 0; j < n; j++) {
        web_idle_slot_t *s = slot_find(fds[j]);
        if (!s) {
            web_idle_touch(fds[j], now_us);   /* unknown: start its idle clock now */
        } else if (now_us - s->last_us >= (int64_t)WEB_IDLE_CLOSE_MS * 1000) {
            if (httpd_sess_trigger_close(hd, fds[j]) == ESP_OK) {
                s->fd = -1;
                closed++;
            }
        }
    }
    s_closed += (uint32_t)closed;
    return closed;
}

static void sweep_work(void *arg)
{
    httpd_handle_t hd = arg;
    size_t n = WEB_IDLE_SLOTS;
    int fds[WEB_IDLE_SLOTS];
    if (httpd_get_client_list(hd, &n, fds) == ESP_OK)
        web_idle_sweep_fds(hd, fds, n, esp_timer_get_time());
}

static void sweep_timer(void *arg)
{
    (void)arg;
    if (s_server) httpd_queue_work(s_server, sweep_work, s_server);
}

void web_idle_reset(void)
{
    for (int i = 0; i < WEB_IDLE_SLOTS; i++) s_slots[i] = (web_idle_slot_t){ .fd = -1 };
}

void web_idle_start(httpd_handle_t hd)
{
    web_idle_reset();
    s_server = hd;
    if (!s_timer) {
        const esp_timer_create_args_t args = { .callback = sweep_timer, .name = "web_idle" };
        if (esp_timer_create(&args, &s_timer) != ESP_OK) {
            ESP_LOGW(TAG, "idle sweep unavailable; sessions close only when the client closes");
            s_timer = NULL;
            return;
        }
    }
    esp_timer_stop(s_timer);
    esp_timer_start_periodic(s_timer, 1000 * 1000);
}

void web_idle_stop(void)
{
    if (s_timer) esp_timer_stop(s_timer);
    s_server = NULL;
}

uint32_t web_idle_closed(void) { return s_closed; }
