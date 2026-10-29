"""Actual power-event state machine and publisher; mock MQTT, not hardware/HA."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
header = (ROOT / 'main/mqtt_integration.h').read_text(encoding='utf-8')
config = 'typedef struct {' + header.split('typedef struct {', 1)[1].split('} mqtt_integration_config_t;', 1)[0] + '} mqtt_integration_config_t;\n'
publisher = source[source.index('static __attribute__((noinline)) bool publish_power_event'):source.index('static void manager_task')]
program = r'''
#include <assert.h>
#include <string.h>
#include "mqtt_power_event.h"
''' + config + r'''
_Static_assert(sizeof(mqtt_integration_config_t)==496,"MQTT config must not grow");
_Static_assert(sizeof(mqtt_power_event_t)==16,"Boot event fits sixteen bytes of the existing task stack");
static unsigned calls;static int publish_result=1;static char last[160];
static int64_t esp_timer_get_time(void){return 123000000;}
static int publish(const char *topic,const char *payload,int retain){
 assert(!strcmp(topic,"home/gateway/event/power")&&!retain);calls++;
 assert(strlen(payload)<sizeof last);strcpy(last,payload);return publish_result;
}
''' + publisher + r'''
int main(void){
 mqtt_power_event_t s;
 for(unsigned flags=0;flags<8;flags++){
  bool power=flags&1,enabled=flags&2,selected=flags&4;
  mqtt_power_event_init(&s,123,power,enabled,selected);
  assert(s.pending==(power&&enabled&&selected));
  assert(s.selected_at_boot==s.pending);
  assert(!mqtt_power_event_due(&s,enabled,selected,false,true,0));
  assert(!mqtt_power_event_due(&s,enabled,selected,true,false,0));
  assert(mqtt_power_event_due(&s,enabled,selected,true,true,0)==(power&&enabled&&selected));
 }
 /* First enabling, an ordinary reboot, and disabling/re-enabling never
  * manufacture a power event. A reconnect retains one pending event. */
 mqtt_power_event_init(&s,1,true,false,true);
 assert(!mqtt_power_event_due(&s,true,true,true,true,100));
 mqtt_power_event_init(&s,1,false,true,true);
 assert(!mqtt_power_event_due(&s,true,true,true,true,100));
 mqtt_power_event_init(&s,1,true,true,true);
 assert(!mqtt_power_event_due(&s,false,true,true,true,100));
 assert(!mqtt_power_event_due(&s,true,true,true,true,200));
 mqtt_power_event_init(&s,1,true,true,true);mqtt_power_event_cancel(&s);assert(!s.selected_at_boot);
 assert(!mqtt_power_event_due(&s,true,true,true,true,0));
 mqtt_power_event_init(&s,0,true,true,true);assert(s.boot_id==1);
 for(int i=0;i<5;i++){
  uint64_t now=(uint64_t)i*30000;
  assert(mqtt_power_event_due(&s,true,true,true,true,now));
  mqtt_power_event_result(&s,false,now);
  assert(!mqtt_power_event_due(&s,true,true,true,true,now+1));
 }
 assert(!s.pending&&s.attempts==5);
 mqtt_power_event_init(&s,1,true,true,true);
 mqtt_power_event_result(&s,false,UINT64_MAX-10);assert(s.retry_at_ms==UINT64_MAX);
 mqtt_integration_config_t cfg={0};strcpy(cfg.base_topic,"home/gateway");
 mqtt_power_event_init(&s,0x1234abcd,true,true,true);
 char tiny[2];assert(!mqtt_power_event_json(tiny,sizeof tiny,&s,UINT64_MAX)&&tiny[1]==0);
 assert(!mqtt_power_event_json(NULL,0,&s,0));
 publish_result=-1;assert(!publish_power_event(&cfg,&s));assert(calls==1);
 mqtt_power_event_result(&s,false,0);assert(!mqtt_power_event_due(&s,true,true,true,true,29999));
 assert(mqtt_power_event_due(&s,true,true,true,true,30000));
 publish_result=1;assert(publish_power_event(&cfg,&s));mqtt_power_event_result(&s,true,30000);
 for(unsigned i=0;i<100;i++)assert(!mqtt_power_event_due(&s,true,true,(i&1)!=0,true,40000+i));
 assert(s.boot_id==0x1234abcd&&calls==2);printf("PAYLOAD %s\n",last);
 assert(!publish_power_event(&cfg,&s)&&calls==2);
 puts("PASS: boot-only opt-in, no WiFi/MQTT reconnect replay, cancel/reenable, bounded retries, backpressure, non-retained event, unchanged config size");
}
'''
with tempfile.TemporaryDirectory(prefix='mqtt-power-') as folder:
    p = Path(folder)
    (p / 'test.c').write_text(program, encoding='utf-8')
    binary = p / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    if os.environ.get('MQTTPOWER_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(p / 'test.c'), '-o', str(binary)], check=True)
    output = subprocess.check_output([str(binary)], text=True, timeout=15)
    payload = json.loads(next(line[8:] for line in output.splitlines() if line.startswith('PAYLOAD ')))
    assert payload == dict(event_type='possible_blackout', boot_id='1234abcd', reset_reason='power_on', uptime_s=123)
    print(output.splitlines()[-1])
