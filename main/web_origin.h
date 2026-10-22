/* Browser origin checks supplement sessions; native clients without Origin
 * remain supported. web_origin_matches is not authentication; together with
 * web_host_trusted it narrows CSRF and DNS-rebinding exposure only. */
#pragma once
#include <stdbool.h>
#include <ctype.h>
#include <string.h>
#include <strings.h>
static inline bool web_origin_matches(const char *host,const char *origin) {
    if (!host || !*host || !origin) return false;
    const char *authority;
    if (!strncasecmp(origin,"http://",7)) authority=origin+7;
    else if (!strncasecmp(origin,"https://",8)) authority=origin+8;
    else return false;
    size_t n=strcspn(authority,"/?#");
    if (!n || strchr(authority,'@') || strlen(host)!=n || strncasecmp(authority,host,n)) return false;
    return !authority[n] || (authority[n]=='/' && !authority[n+1]);
}

static inline bool web_host_port_valid(const char *port) {
    if (!*port) return true;
    if (*port++!=':' || !*port || strlen(port)>5) return false;
    unsigned value=0;
    for (; *port; port++) {
        if (!isdigit((unsigned char)*port)) return false;
        value=value*10+(unsigned)(*port-'0');
    }
    return value>0 && value<=65535;
}

static inline bool web_host_ipv4(const char *s,size_t n) {
    unsigned parts=0,value=0,digits=0;
    for (size_t i=0;i<=n;i++) {
        if (i==n || s[i]=='.') {
            if (!digits || value>255 || (digits>1 && s[i-digits]=='0')) return false;
            parts++;value=0;digits=0;continue;
        }
        if (!isdigit((unsigned char)s[i]) || ++digits>3) return false;
        value=value*10+(unsigned)(s[i]-'0');
    }
    return parts==4;
}

/* Hosts that a public DNS-rebinding attacker cannot serve a page from:
 * IP literals, single-label names and non-public or Tailscale-controlled
 * suffixes. A custom public domain is refused only where a caller applies
 * this check (no web password configured, initial setup). */
static inline bool web_host_trusted(const char *host) {
    if (!host || !*host || strlen(host)>253) return false;
    if (host[0]=='[') {
        const char *end=strchr(host,']');
        if (!end || end==host+1 || !web_host_port_valid(end+1)) return false;
        for (const char *p=host+1;p<end;p++)
            if (!isxdigit((unsigned char)*p) && *p!=':' && *p!='.') return false;
        return memchr(host+1,':',(size_t)(end-host-1))!=NULL;
    }
    size_t n=strcspn(host,":");
    if (!n || !web_host_port_valid(host+n)) return false;
    if (web_host_ipv4(host,n)) return true;
    if (host[n-1]=='.') n--;
    if (!n) return false;
    bool dotted=false;
    for (size_t i=0;i<n;i++) {
        unsigned char c=(unsigned char)host[i];
        if (c=='.') {
            if (!i || host[i-1]=='.') return false;
            dotted=true;
        } else if (!isalnum(c) && c!='-' && c!='_') return false;
    }
    if (!dotted) return true;
    static const char *const suffixes[]={".local",".lan",".home.arpa",".internal",
        ".localdomain",".home",".ts.net",".localhost"};
    for (size_t i=0;i<sizeof suffixes/sizeof suffixes[0];i++) {
        size_t m=strlen(suffixes[i]);
        if (n>m && !strncasecmp(host+n-m,suffixes[i],m)) return true;
    }
    return false;
}
