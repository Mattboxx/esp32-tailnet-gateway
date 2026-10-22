"""Actual MQTT command handler with fixture modules (no broker, no device).

Covers prefix scoping, strict switch payloads, persistence-before-RAM for
Tailscale flags, exit-node conflict refusal, binding-qualified rule toggles
and destination tests, WoL/recovery parsing, service-watch toggling.
MQTTCMD_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
def function(signature):
    at = source.index(signature); return source[at:source.index('\n}', at) + 2] + '\n'

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "control_validation.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define TAILNET_FORWARD_MAX 8
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
typedef struct {char base_topic[96];} mqtt_integration_config_t;
typedef struct {bool enabled, notify; uint32_t interval_s;} service_watch_config_t;
typedef struct {bool enabled; char lan_cidr[20]; uint16_t site_id;} fourvia6_status_t;
static bool s_publish_requested,s_discovery_requested,s_wifi_reconnect_requested;
static int32_t tailscale_enabled=1,tailscale_accept_routes,tailscale_advertise_ap,tailscale_advertise_exit_node,tailscale_lan_bypass,tailscale_snat_subnet_routes;
static uint32_t tailscale_exit_node_ip;
static int restarts,nvs_writes,nvs_fail,forward_calls,forward_index,test_calls,test_index,wol_calls,recover_calls,watch_sets,health_sets;
static uint32_t forward_token,test_token;static bool forward_enabled,recover_remote,health_on,ap_auto_off=true,power_save;
static char wol_mac[32],recover_mac[32];static service_watch_config_t watch={.interval_s=900};
static void mqtt_integration_get_config(mqtt_integration_config_t *c){strcpy(c->base_topic,"home/gw");}
static const char *esp_err_to_name(esp_err_t e){(void)e;return "ERR";}
static esp_err_t nvs_param_set_int(const char *k,int32_t v){(void)k;(void)v;nvs_writes++;return nvs_fail?ESP_FAIL:ESP_OK;}
static esp_err_t nvs_param_set_u8(const char *k,uint8_t v){(void)k;(void)v;nvs_writes++;return nvs_fail?ESP_FAIL:ESP_OK;}
static void schedule_restart(void){restarts++;}
static bool wifi_ap_policy_auto_off(void){return ap_auto_off;}
static void wifi_ap_policy_set_auto_off(bool v){ap_auto_off=v;}
static esp_err_t wifi_power_save_set(bool v){power_save=v;return ESP_OK;}
static void fourvia6_get_status(fourvia6_status_t *s){*s=(fourvia6_status_t){0};}
static esp_err_t fourvia6_set_config(bool e,const char *c,uint16_t s,char *err,size_t n){(void)e;(void)c;(void)s;(void)err;(void)n;return ESP_FAIL;}
static esp_err_t health_monitor_set_enabled(bool v){health_on=v;health_sets++;return ESP_OK;}
static esp_err_t tailnet_forward_set_enabled_bound(int i,uint32_t t,bool e){forward_calls++;forward_index=i;forward_token=t;forward_enabled=e;return ESP_OK;}
static esp_err_t service_check_request(int i,uint32_t t){test_calls++;test_index=i;test_token=t;return ESP_OK;}
static esp_err_t wol_send_saved_mac_text(const char *m){wol_calls++;snprintf(wol_mac,sizeof wol_mac,"%s",m);return ESP_OK;}
static esp_err_t homelab_ops_command(const char *m,bool remote){recover_calls++;recover_remote=remote;snprintf(recover_mac,sizeof recover_mac,"%s",m);return ESP_OK;}
static void service_watch_get(service_watch_config_t *o){*o=watch;}
static esp_err_t service_watch_set(const service_watch_config_t *c){watch_sets++;watch=*c;return ESP_OK;}
''' + function('static bool set_tailscale_flag(') + function('static void handle_command(') + r'''
#define CMD(t,p) handle_command("home/gw/command/" t,p)
int main(void){
    /* Other prefixes are ignored entirely. */
    handle_command("other/command/restart","PRESS");handle_command("home/gwx/command/restart","x");assert(!restarts);
    CMD("restart","");assert(restarts==1);
    /* Strict switch payloads: rejected ones change nothing and only republish state. */
    const char *bad[]={"","yes","2","ON ","true\n","PRESS"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){s_publish_requested=false;CMD("accept_routes",bad[i]);assert(!tailscale_accept_routes&&!nvs_writes&&s_publish_requested);}
    CMD("accept_routes","ON");assert(tailscale_accept_routes==1&&nvs_writes==1);
    CMD("accept_routes","on");assert(nvs_writes==1); /* unchanged: no write */
    nvs_fail=1;CMD("snat_subnet_routes","1");assert(!tailscale_snat_subnet_routes);nvs_fail=0; /* persist before RAM */
    /* Exit-node advertisement refused while another exit node is selected. */
    tailscale_exit_node_ip=0x64400009;int before=nvs_writes;CMD("advertise_exit_node","ON");assert(!tailscale_advertise_exit_node&&nvs_writes==before);
    tailscale_exit_node_ip=0;CMD("advertise_exit_node","ON");assert(tailscale_advertise_exit_node==1&&restarts==2);
    /* Rule toggle needs index AND token; malformed forms never reach the forwarder. */
    const char *rules[]={"tailnet_forward/1","tailnet_forward/9/0000abcd","tailnet_forward/1/0000abc","tailnet_forward/1/0000abcz",
                         "tailnet_forward/1/00000000","tailnet_forward/1x0000abcd","tailnet_forward/1/0000abcd0"};
    for(unsigned i=0;i<sizeof rules/sizeof *rules;i++){char t[96];snprintf(t,sizeof t,"home/gw/command/%s",rules[i]);handle_command(t,"ON");}
    assert(!forward_calls);
    CMD("tailnet_forward/3/0000abcd","OFF");assert(forward_calls==1&&forward_index==3&&forward_token==0xabcd&&!forward_enabled);
    /* Destination test button: PRESS only, same binding rule. */
    CMD("tailnet_test/2/00001234","ON");CMD("tailnet_test/2","PRESS");CMD("tailnet_test/8/00001234","PRESS");CMD("tailnet_test/2/00000000","PRESS");assert(!test_calls);
    CMD("tailnet_test/2/00001234","PRESS");assert(test_calls==1&&test_index==2&&test_token==0x1234);
    /* WoL: compact MAC expanded; recovery only with PRESS/1 and marked remote. */
    CMD("wol/aabbccddeeff","");assert(wol_calls==1&&!strcmp(wol_mac,"aa:bb:cc:dd:ee:ff"));
    CMD("recovery/aabbccddeeff","ON");CMD("recovery/aabbcc","PRESS");assert(!recover_calls);
    CMD("recovery/aabbccddeeff","PRESS");assert(recover_calls==1&&recover_remote&&!strcmp(recover_mac,"aa:bb:cc:dd:ee:ff"));
    /* Service watch: only the enable bit changes. */
    watch=(service_watch_config_t){.enabled=false,.notify=true,.interval_s=300};
    CMD("service_watch_enabled","maybe");assert(!watch_sets);
    CMD("service_watch_enabled","ON");assert(watch_sets==1&&watch.enabled&&watch.notify&&watch.interval_s==300);
    CMD("health_monitor_enabled","1");assert(health_on&&health_sets==1);
    CMD("ap_always_on","ON");assert(!ap_auto_off);
    CMD("reconnect_wifi","");assert(s_wifi_reconnect_requested);
    CMD("unknown_command","ON");
    puts("PASS: actual MQTT command handler: prefix scope, strict payloads, persist-before-RAM, exit-node conflict, binding-qualified rule toggle/test, WoL/recovery parsing, watch toggle (fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='mqtt-commands-') as folder:
    path = Path(folder); (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-parameter', '-I', str(ROOT / 'main')]
    if os.environ.get('MQTTCMD_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
