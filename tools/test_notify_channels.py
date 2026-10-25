"""Actual notification core of main/notify_channels.c with a scripted SMTP peer.

Covered: settings validation (Telegram token and chat id, SMTP host, port,
addresses, header/command injection through CR/LF, user/password pairing),
Base64, the Telegram JSON body (escaping, limits), which events are sent,
and the SMTP dialogue against a fake server: implicit TLS and STARTTLS
(refused when not offered: the password is never sent in clear), AUTH PLAIN
and LOGIN, multi-line and split replies, every refusal code, a silent or
disconnecting server, a server that is not SMTP, oversize replies and the
exact message (headers, Base64 body, terminator). Real TLS, certificates,
DNS, Telegram and real mail servers are NOT covered.
NOTIFY_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / 'main/notify_channels.c').read_text(encoding='utf-8')
core = core.split('/* --- notify core (begin) --- */', 1)[1].split('/* --- notify core (end) --- */', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "history.h"
#include "notify_channels.h"
''' + core + r'''
/* --- scripted SMTP peer: replies[i] answers the i-th read; a NULL ends the connection --- */
typedef struct {const char *const *replies; int next; char sent[8192]; size_t sent_len; int tls; int starttls_result; int fail_send_after; int sends;} peer_t;
static int p_send(void *c, const char *d, size_t n){peer_t *p=c;if(p->fail_send_after>=0&&p->sends++>=p->fail_send_after)return -1;
    size_t k=n>3?n/2:n;   /* partial writes */
    assert(p->sent_len+k<sizeof p->sent);memcpy(p->sent+p->sent_len,d,k);p->sent_len+=k;p->sent[p->sent_len]=0;return (int)k;}
static int p_recv(void *c, char *o, size_t cap){peer_t *p=c;const char *r=p->replies[p->next];if(!r)return 0;p->next++;
    size_t n=strlen(r);if(n>cap)n=cap;memcpy(o,r,n);return (int)n;}
static int p_starttls(void *c){peer_t *p=c;p->tls=1;return p->starttls_result;}
static esp_err_t run(peer_t *p, notify_mail_t *m, char *why){
    p->fail_send_after=p->fail_send_after?p->fail_send_after:-1;
    notify_smtp_io_t io={p,p_send,p_recv,p_starttls};return notify_smtp_send(&io,m,why,192);}
static notify_mail_t mail(void){notify_mail_t m={.helo="gw",.user="me@example.com",.pass="s3cret pass",.from="me@example.com",.to="you@example.org",
    .subject="gw: Tailnet connection lost",.body="Tailnet connection lost at 14:05.\nSecond line.",.date="Sat, 24 Oct 2026 12:00:00 +0000",.starttls=false};return m;}

static void config_tests(void){
    char why[120];
    notify_config_t c;memset(&c,0,sizeof c);c.mail_port=465;
    assert(notify_config_valid(&c,why,sizeof why));                              /* all off is valid */
    c.tg_enabled=true;strcpy(c.tg_token,"123456789:AAH4kq_ZXcvbnm-1234567890qwertyuiopASD");strcpy(c.tg_chat,"123456789");
    assert(notify_config_valid(&c,why,sizeof why));
    strcpy(c.tg_chat,"-1001234567890");assert(notify_config_valid(&c,why,sizeof why));
    strcpy(c.tg_chat,"@my_channel");assert(notify_config_valid(&c,why,sizeof why));
    const char *bad_chats[]={"","-","@abc","12a","@bad-name","123456789012345678901","@"};
    for(unsigned i=0;i<sizeof bad_chats/sizeof *bad_chats;i++){strcpy(c.tg_chat,bad_chats[i]);assert(!notify_config_valid(&c,why,sizeof why)&&why[0]);}
    strcpy(c.tg_chat,"42");
    const char *bad_tokens[]={"","123456789","1234:AAH4kq_ZXcvbnm-1234567890qwertyuiop","12345678x:AAH4kq_ZXcvbnm-1234567890qwertyuiop",
        "123456789:short","123456789:AAH4kq_ZXcvbnm-1234567890qwertyuiop/x","123456789:AAH4kq ZXcvbnm-1234567890qwertyuiop"};
    for(unsigned i=0;i<sizeof bad_tokens/sizeof *bad_tokens;i++){strcpy(c.tg_token,bad_tokens[i]);assert(!notify_config_valid(&c,why,sizeof why));}
    c.tg_enabled=false;assert(notify_config_valid(&c,why,sizeof why));          /* off: not checked */
    c.mail_enabled=true;strcpy(c.mail_host,"smtp.example.com");strcpy(c.mail_from,"gw@example.com");strcpy(c.mail_to,"me+alerts@example.org");
    strcpy(c.mail_user,"gw@example.com");strcpy(c.mail_pass,"p@ss word!");
    assert(notify_config_valid(&c,why,sizeof why));
    c.mail_pass[0]=0;assert(!notify_config_valid(&c,why,sizeof why));c.mail_user[0]=0;assert(notify_config_valid(&c,why,sizeof why));   /* both or neither */
    strcpy(c.mail_user,"gw");strcpy(c.mail_pass,"x\r\nRCPT TO:<evil@x.y>");assert(!notify_config_valid(&c,why,sizeof why));   /* injection */
    strcpy(c.mail_pass,"ok");strcpy(c.mail_user,"g\x01w");assert(!notify_config_valid(&c,why,sizeof why));strcpy(c.mail_user,"gw");
    const char *bad_mail[]={"","a","a@b","@example.com","a@@example.com","a b@example.com","a@example.com>","a@-example.com","a@example..com","a@example.com.",
        "a@example.com\r\nBcc: x@y.z","a<b@example.com"};
    for(unsigned i=0;i<sizeof bad_mail/sizeof *bad_mail;i++){char keep[96];strcpy(keep,c.mail_to);strcpy(c.mail_to,bad_mail[i]);assert(!notify_config_valid(&c,why,sizeof why));strcpy(c.mail_to,keep);
        strcpy(keep,c.mail_from);strcpy(c.mail_from,bad_mail[i]);assert(!notify_config_valid(&c,why,sizeof why));strcpy(c.mail_from,keep);}
    const char *bad_hosts[]={"","-smtp.example.com","smtp.example.com.","smtp..example.com","smtp_example.com","smtp.example.com:465","s mtp.example.com"};
    for(unsigned i=0;i<sizeof bad_hosts/sizeof *bad_hosts;i++){char keep[64];strcpy(keep,c.mail_host);strcpy(c.mail_host,bad_hosts[i]);assert(!notify_config_valid(&c,why,sizeof why));strcpy(c.mail_host,keep);}
    c.mail_port=0;assert(!notify_config_valid(&c,why,sizeof why));c.mail_port=587;
    c.mail_security=2;assert(!notify_config_valid(&c,why,sizeof why));c.mail_security=NOTIFY_STARTTLS;assert(notify_config_valid(&c,why,sizeof why));
    c.level=2;assert(!notify_config_valid(&c,why,sizeof why));
    assert(!notify_config_valid(NULL,why,sizeof why));
}

static void encoding_tests(void){
    char out[64];
    assert(notify_base64("",0,out,sizeof out)==0&&!out[0]);
    assert(notify_base64("f",1,out,sizeof out)==4&&!strcmp(out,"Zg=="));
    assert(notify_base64("fo",2,out,sizeof out)==4&&!strcmp(out,"Zm8="));
    assert(notify_base64("foobar",6,out,sizeof out)==8&&!strcmp(out,"Zm9vYmFy"));
    assert(notify_base64("\0me\0pw",6,out,sizeof out)==8&&!strcmp(out,"AG1lAHB3"));
    assert(notify_base64("foobar",6,out,8)==0&&notify_base64("foobar",6,out,9)==8);   /* room for the NUL */
    char body[1400];
    size_t n=notify_telegram_body(body,sizeof body,"-100123","a \"quote\" \\ and\nnew line \x01 \xE2\x9A\xA0");
    assert(n&&!strcmp(body,"{\"chat_id\":\"-100123\",\"text\":\"a \\\"quote\\\" \\\\ and\\nnew line \\u0001 \xE2\x9A\xA0\",\"disable_web_page_preview\":true}"));
    assert(!notify_telegram_body(body,40,"1","hello there, this does not fit")&&!notify_telegram_body(body,sizeof body,"1","")&&!notify_telegram_body(NULL,9,"1","x"));
    assert(notify_wanted(NOTIFY_PROBLEMS,HIST_EV_TAILNET,HIST_WARN)&&notify_wanted(NOTIFY_PROBLEMS,HIST_EV_CRASH,HIST_ERROR));
    assert(!notify_wanted(NOTIFY_PROBLEMS,HIST_EV_UPLINK,HIST_INFO)&&notify_wanted(NOTIFY_ALL,HIST_EV_UPLINK,HIST_INFO));
    assert(notify_wanted(NOTIFY_PROBLEMS,HIST_EV_SERVICE,HIST_INFO));          /* operational results always */
}

static const char *const EHLO_TLS = "250-smtp.example.com at your service\r\n250-SIZE 35882577\r\n250-8BITMIME\r\n250-AUTH LOGIN PLAIN XOAUTH2\r\n250 SMTPUTF8\r\n";

static void smtp_tests(void){
    char why[192];   /* as the channel status buffer */
    /* Implicit TLS, AUTH PLAIN, reply split across reads. */
    {const char *r[]={"220 smtp.example.com ESMTP\r\n","250-smtp.example.com at your service\r\n250-SIZE 1\r\n","250 AUTH PLAIN LOGIN\r\n","235 2.7.0 Accepted\r\n","250 OK\r\n","250 OK\r\n","354 Go ahead\r\n","250 2.0.0 OK queued\r\n","221 bye\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();
     assert(run(&p,&m,why)==ESP_OK);
     assert(strstr(p.sent,"EHLO gw\r\n")==p.sent);
     assert(strstr(p.sent,"AUTH PLAIN AG1lQGV4YW1wbGUuY29tAHMzY3JldCBwYXNz\r\n"));          /* \0me@example.com\0s3cret pass */
     assert(strstr(p.sent,"MAIL FROM:<me@example.com>\r\nRCPT TO:<you@example.org>\r\nDATA\r\n"));
     assert(strstr(p.sent,"From: <me@example.com>\r\nTo: <you@example.org>\r\nSubject: =?UTF-8?B?Z3c6IFRhaWxuZXQgY29ubmVjdGlvbiBsb3N0?=\r\nDate: Sat, 24 Oct 2026 12:00:00 +0000\r\n"));
     assert(strstr(p.sent,"Content-Transfer-Encoding: base64\r\n\r\nVGFpbG5ldCBjb25uZWN0aW9uIGxvc3QgYXQgMTQ6MDUuClNlY29uZCBsaW5lLg==\r\n.\r\nQUIT\r\n"));
     assert(!p.tls);}
    /* STARTTLS with AUTH LOGIN; the login happens only after TLS. */
    {const char *r[]={"220 mail ESMTP\r\n","250-mail\r\n250-STARTTLS\r\n250 SIZE 10\r\n","220 Ready to start TLS\r\n",EHLO_TLS,"235 ok\r\n","250 ok\r\n","251 forwarded\r\n","354 go\r\n","250 ok\r\n","221 bye\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.starttls=true;
     /* PLAIN is listed after LOGIN: PLAIN is still preferred. */
     assert(run(&p,&m,why)==ESP_OK&&p.tls);
     const char *tls=strstr(p.sent,"STARTTLS\r\n"),*auth=strstr(p.sent,"AUTH ");
     assert(tls&&auth&&auth>tls&&strstr(tls,"EHLO gw\r\n"));}
    {const char *r[]={"220 mail\r\n","250-mail\r\n250-STARTTLS\r\n250 OK\r\n","220 go\r\n","250-mail\r\n250 AUTH=LOGIN\r\n","334 x\r\n","334 y\r\n","235 ok\r\n","250 ok\r\n","250 ok\r\n","354 go\r\n","250 ok\r\n","221 bye\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.starttls=true;
     assert(run(&p,&m,why)==ESP_OK);
     assert(strstr(p.sent,"AUTH LOGIN\r\nbWVAZXhhbXBsZS5jb20=\r\nczNjcmV0IHBhc3M=\r\n"));}
    /* STARTTLS not offered: stop before any login. */
    {const char *r[]={"220 mail\r\n","250-mail\r\n250 AUTH PLAIN\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.starttls=true;
     assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"STARTTLS")&&!strstr(p.sent,"AUTH")&&!strstr(p.sent,"MAIL"));}
    /* "STARTTLSX" is not STARTTLS. */
    {const char *r[]={"220 mail\r\n","250-mail\r\n250 STARTTLSX\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.starttls=true;assert(run(&p,&m,why)!=ESP_OK&&!strstr(p.sent,"STARTTLS\r\n"));}
    /* TLS handshake failure. */
    {const char *r[]={"220 mail\r\n","250-mail\r\n250 STARTTLS\r\n","220 go\r\n",NULL};
     peer_t p={.replies=r,.starttls_result=-1};notify_mail_t m=mail();m.starttls=true;
     assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"TLS")&&!strstr(p.sent,"AUTH"));}
    /* No supported login method; "XPLAIN" is not PLAIN. */
    {const char *r[]={"220 mail\r\n","250-mail\r\n250 AUTH XPLAIN CRAM-MD5\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"login")&&!strstr(p.sent,"AUTH"));}
    /* Refusals at every step, with the server's reason. */
    const char *steps[][12]={
        {"554 no service\r\n",NULL},
        {"220 a\r\n","501 bad helo\r\n",NULL},
        {"220 a\r\n","250 AUTH PLAIN\r\n","535 5.7.8 Username and Password not accepted\r\n",NULL},
        {"220 a\r\n","250 AUTH PLAIN\r\n","235 ok\r\n","553 sender rejected\r\n",NULL},
        {"220 a\r\n","250 AUTH PLAIN\r\n","235 ok\r\n","250 ok\r\n","550 no such user\r\n",NULL},
        {"220 a\r\n","250 AUTH PLAIN\r\n","235 ok\r\n","250 ok\r\n","250 ok\r\n","451 try later\r\n",NULL},
        {"220 a\r\n","250 AUTH PLAIN\r\n","235 ok\r\n","250 ok\r\n","250 ok\r\n","354 go\r\n","552 too big\r\n",NULL}};
    for(unsigned i=0;i<sizeof steps/sizeof *steps;i++){peer_t p={.replies=steps[i]};notify_mail_t m=mail();why[0]=0;
        assert(run(&p,&m,why)!=ESP_OK&&why[0]);}
    {peer_t p={.replies=steps[2]};notify_mail_t m=mail();run(&p,&m,why);assert(strstr(why,"535 5.7.8 Username and Password not accepted"));assert(strstr(why,"app password"));}
    /* Sign-in required without a user: what to do comes first, the server text stays. */
    {const char *r[]={"220 a\r\n","250 OK\r\n","530 5.7.0 Authentication Required\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.user=m.pass="";run(&p,&m,why);
     assert(!strncmp(why,"sign-in required",16)&&strstr(why,"sender: 530 5.7.0 Authentication Required"));}
    /* No login when no user is set. */
    {const char *r[]={"220 a\r\n","250 OK\r\n","250 ok\r\n","250 ok\r\n","354 go\r\n","250 ok\r\n","221 bye\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.user="";assert(run(&p,&m,why)==ESP_OK&&!strstr(p.sent,"AUTH"));}
    /* Silent server, disconnect in the middle, garbage, oversize reply, failing sends. */
    {const char *r[]={NULL};peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"no answer"));}
    {const char *r[]={"220 a\r\n250-par",NULL};peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK);}
    {const char *r[]={"HTTP/1.1 400 Bad Request\r\n",NULL};peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"not SMTP"));}
    {const char *r[]={"22\r\n",NULL};peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK);}
    {static char big[1100];memset(big,'x',sizeof big-1);memcpy(big,"220-",4);const char *r[]={big,big,NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"too long"));}
    {const char *r[]={"220 a\r\n","250 AUTH PLAIN\r\n",NULL};peer_t p={.replies=r,.fail_send_after=1};notify_mail_t m=mail();
     assert(run(&p,&m,why)!=ESP_OK&&strstr(why,"connection lost"));}
    /* Server text in the reason is sanitised. */
    {const char *r[]={"554 bad \x01\x7f text\r\n",NULL};peer_t p={.replies=r};notify_mail_t m=mail();run(&p,&m,why);assert(strstr(why,"554 bad ?? text"));}
    /* A long body is split into Base64 lines of at most 76 characters. */
    {static char longbody[400];memset(longbody,'.',sizeof longbody-1);
     const char *r[]={"220 a\r\n","250 OK\r\n","250 ok\r\n","250 ok\r\n","354 go\r\n","250 ok\r\n","221 bye\r\n",NULL};
     peer_t p={.replies=r};notify_mail_t m=mail();m.user=NULL;m.body=longbody;m.date=NULL;assert(run(&p,&m,why)==ESP_OK&&!strstr(p.sent,"Date:"));
     const char *at=strstr(p.sent,"\r\n\r\n")+4;
     for(const char *line=at;*line!='.';){const char *end=strstr(line,"\r\n");assert(end&&end-line<=76&&*line!='.');line=end+2;}}
    notify_mail_t m=mail();m.from=NULL;peer_t p={0};assert(run(&p,&m,why)==ESP_ERR_INVALID_ARG);
}

int main(void){config_tests();encoding_tests();smtp_tests();puts("notify core: ok");return 0;}
'''

ESP_ERR = '''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
'''


def main():
    with tempfile.TemporaryDirectory(prefix='notify-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'notify.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('notify.exe' if os.name == 'nt' else 'notify')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('NOTIFY_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'notify.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
