/* Host-only regression tests: gcc -std=c11 -Wall -Wextra -Werror
 * tools/test_control_validation.c -o build/control-tests.exe */
#include <assert.h>
#include <stdio.h>
#include "../main/control_validation.h"
#include "../main/web_origin.h"
#include "../components/dhcpserver/include/dhcps_validation.h"

static void test_dhcp(void)
{
    uint8_t packet[1501] = {1, 1, 6};
    packet[236] = 99; packet[237] = 130; packet[238] = 83; packet[239] = 99;
    packet[240] = 53; packet[241] = 1; packet[242] = 1; packet[243] = 255;
    assert(dhcps_request_valid(packet, 244));
    assert(dhcps_request_valid(packet, 1500));
    assert(!dhcps_request_valid(packet, sizeof packet));
    for (size_t length = 0; length < 244; ++length)
        assert(!dhcps_request_valid(packet, length));
    packet[0] = 2;
    assert(!dhcps_request_valid(packet, 244));
    packet[0] = 1;
    packet[243] = 0; /* PAD is a single byte. */
    packet[244] = 255;
    assert(dhcps_request_valid(packet, 245));
    packet[243] = 12; packet[244] = 255; /* Truncated hostname. */
    assert(!dhcps_request_valid(packet, 245));
    packet[244] = 0; packet[245] = 255;
    assert(dhcps_request_valid(packet, 246));
    packet[243] = 50; packet[244] = 0; /* Requested IP needs four bytes. */
    assert(!dhcps_request_valid(packet, 246));
    packet[243] = 53; packet[244] = 1; packet[245] = 3; packet[246] = 255;
    assert(!dhcps_request_valid(packet, 247)); /* Conflicting message types. */
    assert(!dhcps_request_valid(NULL, 300));
}

int main(void)
{
    test_dhcp();
    assert(web_origin_matches("192.0.2.1:8080","http://192.0.2.1:8080"));
    assert(web_origin_matches("router.example","https://ROUTER.example/"));
    assert(!web_origin_matches("router.example","https://router.example.evil"));
    assert(!web_origin_matches("router.example","https://router.example@evil"));
    assert(!web_origin_matches("router.example","null"));
    assert(!web_origin_matches("router.example","http://router.example/path"));
    const char *on[] = {"ON", "on", "1", "true", "TrUe"};
    const char *off[] = {"OFF", "off", "0", "false", "FaLsE"};
    const char *bad[] = {"", "typo", "2", "ON ", " OFF", "true\n", "PRESS", "null"};
    bool value = false;
    for (unsigned i=0; i<sizeof on/sizeof on[0]; i++) {
        assert(control_parse_bool(on[i], &value) && value);
        assert(control_parse_bool(off[i], &value) && !value);
    }
    for (unsigned i=0; i<sizeof bad/sizeof bad[0]; i++) {
        value = true;
        assert(!control_parse_bool(bad[i], &value) && value);
    }
    assert(!control_parse_bool(NULL, &value));
    assert(!control_parse_bool("ON", NULL));
    unsigned index = 99;
    assert(control_parse_index("0", 8, &index) && index == 0);
    assert(control_parse_index("7", 8, &index) && index == 7);
    const char *bad_index[] = {"", "-1", "+1", " 1", "1 ", "1x", "8", "4294967296", "99999999999999999999"};
    for (unsigned i=0; i<sizeof bad_index/sizeof bad_index[0]; i++) {
        index = 99;
        assert(!control_parse_index(bad_index[i], 8, &index) && index == 99);
    }
    assert(control_parse_index("32", 33, &index) && index == 32);
    assert(!control_parse_index("33", 33, &index));
    assert(!control_parse_index("0", 0, &index));
    uint32_t token=7;
    assert(control_parse_hex32("0123aBcD",&token)&&token==0x0123abcd);
    assert(control_parse_hex32("ffffffff",&token)&&token==UINT32_MAX);
    const char *bad_token[]={"","1","000000000","0000000g"," 0000001","+0000001","0000001/"};
    for(unsigned i=0;i<sizeof bad_token/sizeof bad_token[0];i++)assert(!control_parse_hex32(bad_token[i],&token));
    assert(control_cpu_pct(2000000, 2000000) == 0);
    assert(control_cpu_pct(2000000, 0) == 100);
    assert(control_cpu_pct(4000000, 2000000) == 50); /* one busy core */
    assert(control_cpu_pct(4000000, 3000000) == 25);
    assert(control_cpu_pct(4000000, 4000100) == 0); /* snapshot jitter */
    assert(control_cpu_pct(0, 0) == 0);
    uint32_t before = UINT32_MAX - 999999u, after = 1000000u;
    uint32_t delta = after - before;
    assert(delta == 2000000u);
    assert(control_cpu_pct(4000000, delta) == 50);
    /* Summing two idle counters in 32 bits used to lose a whole wrap. */
    uint64_t sum = (uint64_t)3000000000u + 3000000000u;
    assert(control_cpu_pct(8000000000ULL, sum) == 25);
    puts("PASS: DHCP request bounds, MQTT booleans, rule indexes, CPU normalization and rollover");
    return 0;
}
