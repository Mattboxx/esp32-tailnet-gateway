/* Telegram and email notifications, next to ntfy.
 *
 * Messages come from the event bus of history.c (starts, crashes, updates,
 * uplink and tailnet changes, security events, settings copies) and from
 * the operational results that ntfy also sends (recovery checks, service
 * rules). By default only warnings and errors, plus operational results.
 *
 * Off by default. Off, nothing runs: the delivery worker (PSRAM stack) is
 * started only while a message waits and exits when the queue is empty.
 * Telegram uses the Bot API over HTTPS; email uses SMTP with TLS from the
 * start (port 465) or STARTTLS (587), certificates verified against the
 * built-in bundle, and never sends the password before TLS. The bot token
 * and the SMTP password are write-only in the API.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define NOTIFY_TEXT_MAX 192

typedef struct {
    bool tg_enabled;
    char tg_token[96];          /* secret */
    char tg_chat[40];
    bool mail_enabled;
    char mail_host[64];
    uint16_t mail_port;
    uint8_t mail_security;      /* NOTIFY_TLS / NOTIFY_STARTTLS */
    char mail_user[96];
    char mail_pass[96];         /* secret */
    char mail_from[96];
    char mail_to[96];
    uint8_t level;              /* NOTIFY_ALL / NOTIFY_PROBLEMS */
} notify_config_t;
enum {NOTIFY_TLS = 0, NOTIFY_STARTTLS = 1};
enum {NOTIFY_PROBLEMS = 0, NOTIFY_ALL = 1};

/* Core (pure, host-tested). */
bool notify_config_valid(const notify_config_t *c, char *why, size_t cap);
size_t notify_base64(const void *in, size_t len, char *out, size_t cap);   /* 0 when it does not fit */
size_t notify_telegram_body(char *out, size_t cap, const char *chat, const char *text);
/* Transport for the SMTP dialogue: >0 bytes, <=0 error or timeout. */
typedef struct {
    void *ctx;
    int (*send)(void *ctx, const char *data, size_t len);
    int (*recv)(void *ctx, char *out, size_t cap);
    int (*starttls)(void *ctx);   /* 0 = TLS established */
} notify_smtp_io_t;
typedef struct {
    const char *helo, *user, *pass, *from, *to, *subject, *body, *date;   /* date: RFC 5322 or NULL */
    bool starttls;
} notify_mail_t;
esp_err_t notify_smtp_send(const notify_smtp_io_t *io, const notify_mail_t *mail, char *why, size_t cap);
/* Which events are sent. */
bool notify_wanted(uint8_t level_setting, unsigned kind, unsigned level);

/* Firmware. */
void notify_channels_init(void);       /* before history_init */
#include "esp_http_server.h"
esp_err_t notify_channels_register_http(httpd_handle_t server);
