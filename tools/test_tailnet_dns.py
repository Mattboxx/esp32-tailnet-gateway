"""Actual tailnet DNS code on host data (no device):

- external/microlink .../ml_dns_config.c (with cJSON): own MagicDNS name and
  DNSConfig from netmaps: IPv4 resolvers only (port 53), DoH/DoT/IPv6 and other
  ports skipped and counted, longest split-DNS route, routes without resolvers
  answered locally, a route whose resolvers were all unsupported dropped (never
  turned into a local NXDOMAIN route), search domains, A extra records only,
  every list bounded, malformed fields skipped, a map without DNSConfig keeps
  the settings, a new DNSConfig replaces them as a whole, reset;
- main/tailnet_names.c core: the query the gateway sends to a route's resolver
  and the parser of its answer (ID, response bit, question, NXDOMAIN, SERVFAIL,
  compression, CNAME before A, truncation, overlong data), and the local reply
  used for extra records.
Run: CJSON_SOURCE=<sdk>/components/json/cJSON/cJSON.c python tools/test_tailnet_dns.py
(Linux may use pkg-config libcjson). TAILNETDNS_SANITIZE=1 adds ASan/UBSan."""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
core = (ROOT / 'main/tailnet_names.c').read_text(encoding='utf-8')
core = core.split('/* --- names core (begin) --- */', 1)[1].split('/* --- names core (end) --- */', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "ml_dns_config.h"
#include "tailnet_names.h"
''' + core + r'''
static void apply(const char *json) {
    cJSON *j = cJSON_Parse(json); assert(j); ml_dns_apply_map(j); cJSON_Delete(j);
}
static uint32_t ip4(int a, int b, int c, int d) {uint8_t q[4] = {(uint8_t)a, (uint8_t)b, (uint8_t)c, (uint8_t)d}; uint32_t v; memcpy(&v, q, 4); return v;}
#define CHECK(c) do { if (!(c)) {printf("FAIL line %d: %s\n", __LINE__, #c); exit(1);} } while (0)

static void config_cases(void) {
    ml_dns_summary_t s; uint32_t ip = 0, a = 0; char self[ML_DNS_NAME_MAX];
    ml_dns_summary(&s); CHECK(!s.present && !s.self[0]);
    CHECK(!ml_dns_self_name(self) && ml_dns_route("x.corp.example", &a) == ML_DNS_ROUTE_NONE && !ml_dns_global_resolver());
    CHECK(!ml_dns_extra_lookup("nas.example", &ip));

    apply("{\"Node\":{\"Name\":\"GW.Tail1234.ts.net.\"},\"DNSConfig\":{\"Proxied\":true,"
          "\"Resolvers\":[{\"Addr\":\"100.64.0.53\"},{\"Addr\":\"1.1.1.1:53\"},{\"Addr\":\"https://dns.example/dns-query\"},"
          "{\"Addr\":\"[2606:4700::1111]:53\"},{\"Addr\":\"9.9.9.9:5353\"},{\"Addr\":\"300.1.1.1\"},{\"Addr\":\"0.0.0.0\"},{\"Addr\":12}],"
          "\"Routes\":{\"corp.example.\":[{\"Addr\":\"10.0.0.53\"}],\"lab.corp.example\":[{\"Addr\":\"10.9.0.53\"},{\"Addr\":\"10.9.0.54\"},{\"Addr\":\"10.9.0.55\"}],"
          "\"ts.net\":[],\"doh.example\":[{\"Addr\":\"https://x\"}],\"bad name!\":[{\"Addr\":\"10.0.0.1\"}]},"
          "\"Domains\":[\"Tail1234.ts.net\",\"corp.example.\",7],"
          "\"ExtraRecords\":[{\"Name\":\"printer.corp.example.\",\"Type\":\"A\",\"Value\":\"10.0.0.9\"},"
          "{\"Name\":\"vault.tail1234.ts.net\",\"Value\":\"100.64.0.77\"},"
          "{\"Name\":\"v6.tail1234.ts.net\",\"Type\":\"AAAA\",\"Value\":\"fd7a::1\"},"
          "{\"Name\":\"txt.tail1234.ts.net\",\"Type\":\"TXT\",\"Value\":\"hello\"},"
          "{\"Name\":\"empty\",\"Type\":\"\",\"Value\":\"\"}]}}");
    ml_dns_summary(&s);
    CHECK(s.present && s.magic_dns && !strcmp(s.self, "gw.tail1234.ts.net"));
    CHECK(s.resolvers == 2 && s.routes == 3 && s.domains == 2 && s.extra == 2);
    /* 6 resolvers + 1 route addr over the bound + 2 skipped routes + 1 domain + 3 records */
    CHECK(s.ignored == 6 + 1 + 1 + 1 + 1 + 1 + 3);
    CHECK(ml_dns_self_name(self) && !strcmp(self, "gw.tail1234.ts.net"));
    CHECK(ml_dns_global_resolver() == ip4(100, 64, 0, 53));
    CHECK(ml_dns_route("host.corp.example", &a) == ML_DNS_ROUTE_FWD && a == ip4(10, 0, 0, 53));
    CHECK(ml_dns_route("CORP.example.", &a) == ML_DNS_ROUTE_FWD);                       /* the domain itself */
    CHECK(ml_dns_route("a.lab.corp.example", &a) == ML_DNS_ROUTE_FWD && a == ip4(10, 9, 0, 53));   /* longest wins */
    CHECK(ml_dns_route("xcorp.example", &a) == ML_DNS_ROUTE_NONE);                       /* label boundary */
    CHECK(ml_dns_route("nas.tail1234.ts.net", NULL) == ML_DNS_ROUTE_LOCAL);
    CHECK(ml_dns_route("x.doh.example", &a) == ML_DNS_ROUTE_NONE);                       /* unsupported-only route dropped */
    CHECK(ml_dns_route("www.example.com", &a) == ML_DNS_ROUTE_NONE && ml_dns_route("", &a) == ML_DNS_ROUTE_NONE);
    CHECK(ml_dns_extra_lookup("Printer.Corp.Example.", &ip) && ip == ip4(10, 0, 0, 9));
    CHECK(ml_dns_extra_lookup("vault.tail1234.ts.net", &ip) && ip == ip4(100, 64, 0, 77));
    CHECK(!ml_dns_extra_lookup("v6.tail1234.ts.net", &ip) && !ml_dns_extra_lookup("txt.tail1234.ts.net", &ip));
    CHECK(ml_dns_extra_lookup_search("printer", &ip) && ip == ip4(10, 0, 0, 9));
    CHECK(ml_dns_extra_lookup_search("VAULT", &ip) && ip == ip4(100, 64, 0, 77));
    CHECK(!ml_dns_extra_lookup_search("printer.corp", &ip) && !ml_dns_extra_lookup_search("ghost", &ip));
    uint32_t v1 = s.version;

    /* A map without DNSConfig keeps everything; the same name is no change. */
    apply("{\"Peers\":[],\"Node\":{\"Name\":\"gw.tail1234.ts.net.\"}}");
    ml_dns_summary(&s); CHECK(s.version == v1 && s.routes == 3 && s.extra == 2);
    apply("{\"Node\":{\"Name\":\"gw2.tail1234.ts.net\"}}");
    ml_dns_summary(&s); CHECK(s.version == v1 + 1 && !strcmp(s.self, "gw2.tail1234.ts.net") && s.routes == 3);
    apply("{\"Node\":{\"Name\":\"bad name\"}}");                                          /* invalid: kept */
    ml_dns_summary(&s); CHECK(!strcmp(s.self, "gw2.tail1234.ts.net"));

    /* A new DNSConfig replaces the previous one as a whole. */
    apply("{\"DNSConfig\":{\"Routes\":{\"other.example\":[{\"Addr\":\"192.168.1.53\"}]}}}");
    ml_dns_summary(&s); CHECK(s.present && !s.magic_dns && s.resolvers == 0 && s.routes == 1 && s.extra == 0 && s.ignored == 0);
    CHECK(ml_dns_route("host.corp.example", &a) == ML_DNS_ROUTE_NONE && !ml_dns_global_resolver());

    /* Malformed fields are skipped, never fatal. */
    apply("{\"DNSConfig\":{\"Resolvers\":\"x\",\"Routes\":[1,2],\"Domains\":{},\"ExtraRecords\":7,\"Proxied\":\"yes\"}}");
    ml_dns_summary(&s); CHECK(s.present && !s.magic_dns && s.resolvers == 0 && s.extra == 0);
    apply("{\"DNSConfig\":5}"); ml_dns_summary(&s); CHECK(s.present);                 /* not an object: ignored */
    apply("{}"); apply("[]");

    /* Bounds: names, lists. */
    char big[8192]; int at = 0;
    at += snprintf(big + at, sizeof big - at, "{\"DNSConfig\":{\"ExtraRecords\":[");
    for (int i = 0; i < 40; i++) at += snprintf(big + at, sizeof big - at, "%s{\"Name\":\"h%d.example\",\"Value\":\"10.1.0.%d\"}", i ? "," : "", i, i + 1);
    at += snprintf(big + at, sizeof big - at, "],\"Routes\":{");
    for (int i = 0; i < 12; i++) at += snprintf(big + at, sizeof big - at, "%s\"r%d.example\":[{\"Addr\":\"10.2.0.%d\"}]", i ? "," : "", i, i + 1);
    at += snprintf(big + at, sizeof big - at, "},\"Domains\":[\"a.x\",\"b.x\",\"c.x\",\"d.x\",\"e.x\",\"f.x\"],"
                   "\"Resolvers\":[{\"Addr\":\"1.0.0.1\"},{\"Addr\":\"1.0.0.2\"},{\"Addr\":\"1.0.0.3\"},{\"Addr\":\"1.0.0.4\"},{\"Addr\":\"1.0.0.5\"}]}}");
    apply(big);
    ml_dns_summary(&s);
    CHECK(s.extra == ML_DNS_MAX_EXTRA && s.routes == ML_DNS_MAX_ROUTES && s.domains == ML_DNS_MAX_DOMAINS && s.resolvers == ML_DNS_MAX_RESOLVERS);
    CHECK(s.ignored == (40 - ML_DNS_MAX_EXTRA) + (12 - ML_DNS_MAX_ROUTES) + 2 + 1);
    CHECK(ml_dns_extra_lookup("h31.example", &ip) && !ml_dns_extra_lookup("h32.example", &ip));
    char longname[200]; memset(longname, 'a', 70); strcpy(longname + 70, ".example");
    char j2[600]; snprintf(j2, sizeof j2, "{\"Node\":{\"Name\":\"%s\"},\"DNSConfig\":{\"ExtraRecords\":[{\"Name\":\"%s\",\"Value\":\"10.0.0.1\"}]}}", longname, longname);
    apply(j2); ml_dns_summary(&s); CHECK(s.extra == 0 && s.ignored == 1 && !strcmp(s.self, "gw2.tail1234.ts.net"));
    CHECK(!ml_dns_extra_lookup(longname, &ip) && ml_dns_route(longname, &a) == ML_DNS_ROUTE_NONE);

    ml_dns_reset(); ml_dns_summary(&s); CHECK(!s.present && !s.self[0]);
}

static int mkans(uint8_t *r, const uint8_t *q, int ql, int rcode, const uint8_t *answers, int alen, int an) {
    memcpy(r, q, (size_t)ql); r[2] = 0x81; r[3] = (uint8_t)(0x80 | rcode); r[6] = 0; r[7] = (uint8_t)an;
    memcpy(r + ql, answers, (size_t)alen); return ql + alen;
}

static void wire_cases(void) {
    uint8_t q[512], r[600], out[600]; uint32_t ip = 0;
    int ql = tailnet_names_query("Host.Corp.Example.", 0xBEEF, q, sizeof q);
    static const uint8_t want[] = {0xBE,0xEF,1,0,0,1,0,0,0,0,0,0,4,'H','o','s','t',4,'C','o','r','p',7,'E','x','a','m','p','l','e',0,0,1,0,1};
    CHECK(ql == (int)sizeof want && !memcmp(q, want, sizeof want));
    CHECK(!tailnet_names_query("a..b", 1, q, sizeof q) && !tailnet_names_query("", 1, q, sizeof q) && !tailnet_names_query(NULL, 1, q, sizeof q));
    char l64[80]; memset(l64, 'a', 64); l64[64] = 0;
    CHECK(!tailnet_names_query(l64, 1, q, sizeof q) && !tailnet_names_query("host.example", 1, q, 20));
    ql = tailnet_names_query("host.corp.example", 0x1234, q, sizeof q);

    static const uint8_t a1[] = {0xC0,0x0C,0,1,0,1,0,0,0,60,0,4,10,0,0,20};
    int rl = mkans(r, q, ql, 0, a1, sizeof a1, 1);
    CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 1 && ip == ip4(10, 0, 0, 20));
    r[13] = 'H'; CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 1); r[13] = 'h';     /* 0x20 case randomisation */
    r[1] ^= 1; CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1); r[1] ^= 1;         /* other ID */
    r[2] = 0x01; CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1); r[2] = 0x81;      /* not a response */
    r[14] = 'x'; CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1); r[14] = 'o';      /* other question */
    CHECK(tailnet_names_parse_a(r, rl - 1, q, ql, &ip) == -1);                            /* truncated rdata */
    CHECK(tailnet_names_parse_a(r, 11, q, ql, &ip) == -1);
    rl = mkans(r, q, ql, 3, NULL, 0, 0); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 0);   /* NXDOMAIN */
    rl = mkans(r, q, ql, 2, NULL, 0, 0); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1);  /* SERVFAIL: no verdict */
    rl = mkans(r, q, ql, 0, NULL, 0, 0); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 0);   /* no data */
    static const uint8_t cname_a[] = {0xC0,0x0C,0,5,0,1,0,0,0,60,0,6,3,'w','w','w',0xC0,0x11,
                                      3,'w','w','w',0xC0,0x11,0,1,0,1,0,0,0,60,0,4,10,0,0,30};
    rl = mkans(r, q, ql, 0, cname_a, sizeof cname_a, 2);
    CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 1 && ip == ip4(10, 0, 0, 30));
    static const uint8_t aaaa[] = {0xC0,0x0C,0,28,0,1,0,0,0,60,0,16,0xfd,0x7a,0,0,0,0,0,0,0,0,0,0,0,0,0,1};
    rl = mkans(r, q, ql, 0, aaaa, sizeof aaaa, 1); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 0);
    static const uint8_t overlong[] = {0xC0,0x0C,0,1,0,1,0,0,0,60,0x01,0x00,1,2,3,4};
    rl = mkans(r, q, ql, 0, overlong, sizeof overlong, 1); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1);
    static const uint8_t badptr[] = {0x80,0x0C,0,1,0,1,0,0,0,60,0,4,1,2,3,4};
    rl = mkans(r, q, ql, 0, badptr, sizeof badptr, 1); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == -1);
    static const uint8_t zero[] = {0xC0,0x0C,0,1,0,1,0,0,0,60,0,4,0,0,0,0};
    rl = mkans(r, q, ql, 0, zero, sizeof zero, 1); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 0);   /* 0.0.0.0 is no address */
    rl = mkans(r, q, ql, 0, a1, sizeof a1, 5); CHECK(tailnet_names_parse_a(r, rl, q, ql, &ip) == 1);        /* the first A decides */
    CHECK(tailnet_names_parse_a(NULL, rl, q, ql, &ip) == -1 && tailnet_names_parse_a(r, rl, q, 3, &ip) == -1);

    /* Local reply for an extra record; question parse of the same query. */
    char name[TN_QNAME_MAX]; uint16_t type = 0;
    int end = tailnet_names_question(q, ql, name, &type);
    CHECK(end == ql && type == 1 && !strcmp(name, "host.corp.example"));
    memset(out, 0xAA, sizeof out);
    int n = tailnet_names_reply(q, end, out, sizeof out, true, ip4(10, 0, 0, 9), type);
    CHECK(n == end + 16 && out[7] == 1 && (out[3] & 0x0F) == 0 && !memcmp(out + end + 12, "\x0a\0\0\x09", 4) && out[n] == 0xAA);
    n = tailnet_names_reply(q, end, out, sizeof out, true, ip4(10, 0, 0, 9), 28);
    CHECK(n == end && out[7] == 0 && (out[3] & 0x0F) == 0);                                /* AAAA: no data */
    n = tailnet_names_reply(q, end, out, sizeof out, false, 0, 1);
    CHECK(n == end && (out[3] & 0x0F) == 3);
    CHECK(!tailnet_names_reply(q, end, out, end + 15, true, 1, 1) && !tailnet_names_reply(q, 5, out, sizeof out, true, 1, 1));
}

int main(void) {
    config_cases();
    wire_cases();
    printf("tailnet DNS: settings and wire cases ok\n");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='tsdns-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'nvs_flags.h').write_text('#pragma once\ntypedef struct {int x;} nvs_flags_t;\n', encoding='utf-8')
        c = path / 'test.c'
        c.write_text(PROGRAM, encoding='utf-8')
        binary = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-overlength-strings', '-DML_DNS_HOST_TEST',
                 '-I', str(path), '-I', str(ROOT / 'main'), '-I', str(ML / 'include')]
        libs = []
        dep = os.environ.get('CJSON_SOURCE')
        if dep:
            flags += ['-I', str(Path(dep).parent), dep]
        else:
            flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
            libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
        if os.environ.get('TAILNETDNS_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), str(ML / 'src/ml_dns_config.c'), '-o', str(binary), *libs], check=True)
        subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == '__main__':
    main()
