"""Control-plane loss setting (main/control_loss.h), compiled on the host, and
how the firmware stores, validates and applies it.

Behaviour (actual header code): mode names and their ML_POLICY_LOSS_* values,
unknown and NULL names, the name of out-of-range stored values (keep), grace
limits 30 s .. 24 h, fractional, negative and huge numbers.
Structure: /api/tailscale validates both fields before the save transaction,
stores them as ts_loss_mode/ts_loss_grace, applies them live only after a
successful save and reports them in GET together with control_stale; boot
load range-checks NVS and applies before MicroLink starts; the web form
sends the grace in seconds from minutes and defaults to keep.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8').replace('\r\n', '\n')


web = text('main/web_ui.c')
mgr = text('main/tailscale_manager.c')
html = text('main/index.html')
policy_h = text('external/microlink/components/microlink/include/ml_policy.h')

post = web[web.index('static esp_err_t tailscale_save_handler('):]
post = post[:post.index('\n}\n')]
check = post.index('control_loss_mode_parse(loss_mode->valuestring) < 0')
assert check < post.index('if (!save_txn_begin()) {'), 'validation must precede every write'
assert '!control_loss_grace_valid(loss_grace->valuedouble)' in post
assert 'save_int_if_present(s, "control_loss_grace_s",  "ts_loss_grace");' in post
assert 'nvs_save_int("ts_loss_mode", control_loss_mode_parse(loss_mode->valuestring));' in post
live = post.index('ml_policy_set_control_loss((uint8_t)tailscale_control_loss_mode,')
assert post.index('if (save_txn_end()) {') < live < post.index('} else {\n        if (v6_written) fourvia6_init();')
assert 'cJSON_AddStringToObject(settings, "control_loss_mode",       control_loss_mode_name(tailscale_control_loss_mode));' in web
assert 'cJSON_AddBoolToObject(runtime, "control_stale", ts_runtime_policy.control_stale);' in web
assert 'int32_t tailscale_control_loss_mode = CONTROL_LOSS_KEEP;' in mgr
assert 'v >= CONTROL_LOSS_KEEP && v <= CONTROL_LOSS_STRICT' in mgr and 'control_loss_grace_valid(v)' in mgr
assert mgr.index('ml_policy_set_control_loss((uint8_t)tailscale_control_loss_mode') < mgr.index('microlink_t *instance = microlink_init(&cfg);')
for name in ('KEEP    0u', 'BOUNDED 1u', 'STRICT  2u'):
    assert '#define ML_POLICY_LOSS_' + name in policy_h, name
assert "document.getElementById('ts-loss-mode').value = s.control_loss_mode || 'keep';" in html
assert "parseInt(document.getElementById('ts-loss-grace').value, 10) || 5)) * 60," in html
assert '<option value="keep">Keep the last policy (like the official client)</option>' in html
assert html.index('<option value="keep">') < html.index('<option value="bounded">') < html.index('<option value="strict">')

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include "control_loss.h"
int main(void) {
    assert(control_loss_mode_parse("keep") == CONTROL_LOSS_KEEP && CONTROL_LOSS_KEEP == 0);
    assert(control_loss_mode_parse("bounded") == CONTROL_LOSS_BOUNDED && CONTROL_LOSS_BOUNDED == 1);
    assert(control_loss_mode_parse("strict") == CONTROL_LOSS_STRICT && CONTROL_LOSS_STRICT == 2);
    assert(control_loss_mode_parse(NULL) < 0 && control_loss_mode_parse("") < 0);
    assert(control_loss_mode_parse("Keep") < 0 && control_loss_mode_parse("keep ") < 0 && control_loss_mode_parse("2") < 0);
    assert(!strcmp(control_loss_mode_name(0), "keep") && !strcmp(control_loss_mode_name(1), "bounded"));
    assert(!strcmp(control_loss_mode_name(2), "strict") && !strcmp(control_loss_mode_name(7), "keep"));
    assert(!strcmp(control_loss_mode_name(-1), "keep"));
    for (int m = 0; m <= 2; m++) assert(control_loss_mode_parse(control_loss_mode_name(m)) == m);
    assert(control_loss_grace_valid(30) && control_loss_grace_valid(300) && control_loss_grace_valid(86400));
    assert(CONTROL_LOSS_GRACE_DEFAULT == 300 && control_loss_grace_valid(CONTROL_LOSS_GRACE_DEFAULT));
    assert(!control_loss_grace_valid(29) && !control_loss_grace_valid(86401) && !control_loss_grace_valid(0));
    assert(!control_loss_grace_valid(-60) && !control_loss_grace_valid(60.5) && !control_loss_grace_valid(1e12));
    puts("PASS: control-loss setting names/values, unknown and NULL names, stored out-of-range mode reads as keep, "
         "grace 30-86400 s (fractional/negative/huge refused); API validates before saving, applies live after a "
         "successful save, boot load range-checks NVS before MicroLink starts, form defaults to keep");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='control-loss-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
