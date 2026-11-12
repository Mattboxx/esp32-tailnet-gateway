"""Run the custom DHCP OFFER/ACK option encoder without the removed SDK flag."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'components/dhcpserver/dhcpserver.c').read_text(encoding='utf-8')
header = (root / 'components/dhcpserver/include/dhcpserver/dhcpserver.h').read_text(encoding='utf-8')


def function(text, start):
    offset = text.index(start)
    return text[offset:text.index('\n}', offset) + 2]


fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8_t;
typedef uint32_t u32_t;
typedef uint8_t dhcps_offer_t;
typedef struct { u32_t addr; } ip4_addr_t;
typedef struct { ip4_addr_t gw; } ip_info_t;
enum { OFFER_ROUTER = 1, OFFER_DNS = 2 };
enum { DNS_TYPE_MAIN, DNS_TYPE_BACKUP };
typedef struct {
    ip4_addr_t server_address, dhcps_mask, dns_server[2];
    dhcps_offer_t dhcps_dns, dhcps_offer;
    unsigned dhcps_lease_time;
    void *dhcps_netif;
    const char *dhcps_captiveportal_uri;
} dhcps_t;
#define DHCPS_LEASE_UNIT 60
#define LWIP_ASSERT(message, condition) assert(condition)
#define ip4_addr1(ip) (((const u8_t *)&(ip)->addr)[0])
#define ip4_addr2(ip) (((const u8_t *)&(ip)->addr)[1])
#define ip4_addr3(ip) (((const u8_t *)&(ip)->addr)[2])
#define ip4_addr4(ip) (((const u8_t *)&(ip)->addr)[3])
#define ip4_addr_isany_val(ip) (!(ip).addr)
static void get_ip_info(void *netif, ip_info_t *out) { (void)netif; *out = (ip_info_t){0}; }
'''

tests = r'''
static ip4_addr_t address(const u8_t octets[4]) {
    ip4_addr_t value;
    memcpy(&value.addr, octets, 4);
    return value;
}

static void check(bool enabled, const u8_t primary[4], const u8_t backup[4],
                  const u8_t *expected, size_t count) {
    dhcps_t state = {
        .server_address = address((const u8_t[]){192, 0, 2, 1}),
        .dhcps_mask = address((const u8_t[]){255, 255, 255, 0}),
        .dns_server = {address(primary), address(backup)},
        .dhcps_dns = enabled ? OFFER_DNS : 0,
        .dhcps_lease_time = 10,
    };
    u8_t options[256] = {0};
    const u8_t *end = add_offer_options(&state, options);
    size_t dns_options = 0;
    for (const u8_t *p = options; p < end;) {
        assert(end - p >= 2);
        const u8_t type = *p++;
        const u8_t size = *p++;
        assert(end - p >= size);
        if (type == DHCP_OPTION_DNS_SERVER) {
            assert(size == count);
            assert(memcmp(p, expected, count) == 0);
            dns_options++;
        }
        p += size;
    }
    assert(dns_options == 1);
}

int main(void) {
    const u8_t none[] = {0, 0, 0, 0};
    const u8_t ap[] = {192, 0, 2, 1};
    const u8_t primary[] = {192, 0, 2, 53};
    const u8_t backup[] = {198, 51, 100, 53};
    const u8_t both[] = {192, 0, 2, 53, 198, 51, 100, 53};
    check(false, primary, backup, ap, sizeof ap);
    check(true, none, none, ap, sizeof ap);
    check(true, primary, none, primary, sizeof primary);
    check(true, none, backup, backup, sizeof backup);
    check(true, primary, backup, both, sizeof both);
}
'''

options = re.findall(r'^#define DHCP_OPTION_[^\n]+', source, re.MULTILINE)
implementation = [
    function(header, 'static inline bool dhcps_router_enabled'),
    function(header, 'static inline bool dhcps_dns_enabled'),
    function(source, 'static inline u8_t* dhcps_option_ip'),
    function(source, 'static u8_t *add_offer_options'),
]
with tempfile.TemporaryDirectory(prefix='dhcps-dns-') as temp:
    path = Path(temp)
    test = path / 'test.c'
    test.write_text('\n'.join([fixture, *options, *implementation, tests]), encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', str(test), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=10)
print('PASS custom DHCP DNS option: recovery fallback and configured primary/backup')
