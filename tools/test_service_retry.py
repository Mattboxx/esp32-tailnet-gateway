"""Actual retry/clock/callback/manager logic with mocked SDK, broker and time."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/mqtt_integration.c').read_text()
def section(start,end):return start+source.split(start,1)[1].split(end,1)[0]
clock=section('static void broker_clock_set','extern bool wifi_ap_policy_auto_off')
callback=section('static void mqtt_event_handler','static bool start_client')
status=section('static void status_update','static void manager_task')
manager=section('static void manager_task','void mqtt_integration_init').replace('while (true)', 'while (fixture_step())')
PROGRAM=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "service_retry.h"
#include "discovery_budget.h"
typedef int esp_err_t;
typedef void *esp_event_base_t;
typedef struct {void *client; int retain,dup,current_data_offset,data_len,total_data_len,topic_len;char *topic,*data;} event_t;
typedef event_t *esp_mqtt_event_handle_t;
typedef struct {bool enabled,broker_watchdog_enabled;char uri[80],base_topic[80],broker_watchdog_wol_mac[18];int interval_seconds,broker_watchdog_timeout_seconds;} mqtt_integration_config_t;
#define BROKER_CONNECTED 1u
#define BROKER_DISCONNECTED 2u
#define MQTT_EVENT_CONNECTED 1
#define MQTT_EVENT_DISCONNECTED 2
#define MQTT_EVENT_DATA 3
#define MQTT_EVENT_ERROR 4
#define ESP_OK 0
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
static int s_broker_clock_mux,client_token;
static void *s_client;
static bool s_connected,s_publish_requested,s_discovery_requested,s_watchdog_triggered,s_restart_requested,s_wifi_reconnect_requested;
static uint32_t s_connection_events,s_watchdog_wake_count;
static int64_t s_last_broker_ok_us,now_us;
static char s_availability_topic[128];
static discovery_budget_t s_discovery;
typedef struct {bool configured,connected,connecting,discovery_pending;uint8_t retry_level;uint32_t retry_in_seconds;uint16_t discovery_entities;} mqtt_integration_status_t;
static mqtt_integration_status_t s_status;static int s_status_mux;
static mqtt_integration_status_t seen[130];
static unsigned tick,starts,reconnects,subscribes,states,discovery,wakes,stops;
static int64_t esp_timer_get_time(void){return now_us;}
static int esp_mqtt_client_stop(void *p){assert(p);stops++;return 0;}
static int esp_mqtt_client_destroy(void *p){assert(p);return 0;}
static void handle_command(const char *a,const char *b){(void)a;(void)b;}
static void mqtt_integration_get_config(mqtt_integration_config_t *c){*c=(mqtt_integration_config_t){.enabled=true,.broker_watchdog_enabled=true,.uri="mqtt://fixture",.base_topic="fixture",.broker_watchdog_wol_mac="00:00:00:00:00:01",.interval_seconds=30,.broker_watchdog_timeout_seconds=30};}
static int publish(const char *a,const char *b,int c){(void)a;(void)b;(void)c;return 0;}
static void publish_state(void){states++;}
static void publish_discovery(void){discovery++;}
static int esp_mqtt_client_subscribe(void *p,const char *t,int qos){assert(p&&t&&qos==1);subscribes++;return 0;}
static bool homelab_ops_admit(void){return true;}
static bool start_client(void){starts++;if(starts<3)return false;s_client=&client_token;return true;}
static int esp_mqtt_client_reconnect(void *p){assert(p);reconnects++;return -1;}
static uint32_t ulTaskNotifyTake(int a,int b){(void)a;(void)b;return 0;}
static void vTaskDelay(int n){(void)n;assert(false);}
static void esp_restart(void){assert(false);}
static int esp_wifi_disconnect(void){assert(false);return 0;}
static int esp_wifi_connect(void){assert(false);return 0;}
static int wol_send_saved_mac_text(const char *m){assert(m[0]);wakes++;return 0;}
static bool fixture_step(void);
'''
TAIL=r'''
static bool fixture_step(void){
    if(tick)seen[tick]=s_status;
    if(++tick>120)return false;
    now_us=(int64_t)tick*1000000;
    event_t ev={.client=s_client};
    if(tick==17||tick==80){assert(s_client);mqtt_event_handler(NULL,NULL,MQTT_EVENT_CONNECTED,&ev);}
    if(tick==20||tick==21||tick==25||tick==85||tick==86){assert(s_client);mqtt_event_handler(NULL,NULL,MQTT_EVENT_DISCONNECTED,&ev);}
    return true;
}
int main(void){
    service_retry_t r={0};assert(service_retry_due(&r,0));
    service_retry_begin(&r,0);assert(!service_retry_due(&r,30000));assert(!service_retry_timed_out(&r,29999));assert(service_retry_timed_out(&r,30000));
    uint64_t now=0;for(unsigned i=0;i<100;i++){service_retry_failed(&r,now);uint64_t delay=r.next_ms-now;assert(delay>=5000&&delay<=300000);assert(!service_retry_due(&r,r.next_ms-1));assert(service_retry_due(&r,r.next_ms));now=r.next_ms;}
    service_retry_reset(&r);assert(!r.failures&&service_retry_due(&r,0));
    now_us=1000000;broker_clock_set(false,true);now_us=5000000;broker_clock_set(false,false);assert(broker_silence_us()==4000000);
    s_client=&client_token;event_t stale={.client=&tick};mqtt_event_handler(NULL,NULL,MQTT_EVENT_CONNECTED,&stale);assert(!s_connected);
    event_t live={.client=s_client};mqtt_event_handler(NULL,NULL,MQTT_EVENT_CONNECTED,&live);assert(s_connected&&!subscribes&&!discovery&&!states);
    stop_client();assert(!s_connected&&!s_connection_events);
    now_us=1;manager_task(NULL);
    assert(starts==3&&reconnects>0&&reconnects<12);
    assert(subscribes==2&&discovery==2&&states>=2);
    assert(wakes==2&&s_watchdog_wake_count==2&&s_watchdog_triggered);
    /* Last failed reconnect did not reset the genuine second outage at 85 s. */
    assert(s_last_broker_ok_us==85000000);
    /* Published status: backoff countdown before the first success, an
     * in-flight attempt, connected with Discovery, then backoff again. */
    unsigned backoff=0,connecting=0,connected=0;
    for(unsigned i=1;i<=120;i++){
        mqtt_integration_status_t s=seen[i];assert(s.configured);
        assert(!(s.connected&&(s.connecting||s.retry_in_seconds)));
        assert(s.retry_in_seconds<=300&&s.retry_level<=7);
        if(s.retry_in_seconds){backoff++;assert(!s.connecting&&s.retry_level);}
        if(s.connecting)connecting++;
        if(s.connected){connected++;assert(!s.retry_level);}
        if(!s.connected)assert(!s.discovery_pending&&!s.discovery_entities);
    }
    assert(backoff&&connecting&&connected);
    assert(seen[3].retry_in_seconds&&!seen[3].connected);
    assert(!seen[16].connected&&seen[17].connected&&seen[19].connected);
    assert(!seen[17].discovery_pending); /* fixture Discovery enumerates no entities */
    assert(!seen[20].connected&&seen[80].connected&&!seen[85].connected);
    mqtt_integration_config_t off={0};service_retry_t idle={.failures=3,.next_ms=999999};s_connected=false;
    status_update(&off,&idle,true,0);assert(!s_status.configured&&!s_status.retry_in_seconds&&!s_status.connecting);
    puts("PASS: actual worker/callback/clock and bounded retry; startup recovery, delayed retry, two outage bursts, stale events, deferred Discovery, published status snapshot (mock SDK/broker)");
}
'''
assert '.network.disable_auto_reconnect = true' in source
assert 'connecting to %s' not in source
with tempfile.TemporaryDirectory(prefix='service-retry-') as folder:
    p=Path(folder);(p/'test.c').write_text(PROGRAM+clock+callback+status+manager+TAIL)
    binary=p/('test.exe' if os.name=='nt' else 'test');flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'main')]
    if os.environ.get('RETRY_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
