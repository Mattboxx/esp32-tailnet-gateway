"""Telegram bot commands (main/telegram_commands.c, 3.0.12) on the host.

The pure core is compiled as is (TG_COMMANDS_HOST_TEST) with cJSON:
- only messages from the configured chat become commands (private chats and
  negative group ids); other chats are counted and skipped;
- messages older than 10 minutes are skipped when the clock is known; non-text
  updates advance the offset but run nothing;
- at most 5 commands per answer, the highest update_id is reported;
- malformed answers ("ok":false, no result array, broken JSON, a NUL escape)
  are invalid as a whole; oversized command texts are dropped;
- "/wol@MyBot nas" becomes "wol nas"; "/info" becomes "info";
- poll interval 5..300 s.
The firmware part is checked in the source: the backlog is skipped on the
first poll, the offset advances before any command runs, oversized answers
are refused, the token is wiped from the URL, the task has no internal-RAM
stack and writes no flash, and ntfy and Telegram share remote_command_run.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main/telegram_commands.c').read_text(encoding='utf-8').replace('\r\n', '\n')
fw = SRC[SRC.index('#ifndef TG_COMMANDS_HOST_TEST'):]
assert 'offset=-1&limit=1&timeout=0' in fw and 's_have_offset = true' in fw
run_at = fw.index('for (int i = 0; i < u.count; i++) run(c, u.cmd[i].text);')
assert fw.rindex('if (u.last_update_id > s_last_update) s_last_update = u.last_update_id;', 0, run_at) < run_at
assert 'if ((size_t)total >= cap - 1) total = -1;' in fw
assert 'memset(url, 0, sizeof url);' in fw and 'memset(token, 0, sizeof token);' in fw
assert 'MALLOC_CAP_SPIRAM) == pdPASS' in fw and 'nvs_param_set' not in fw[:fw.index('esp_err_t telegram_commands_set_config')]
ntfy = (ROOT / 'main/ntfy_integration.c').read_text(encoding='utf-8')
assert 'remote_command_run(message, c->info_enabled, c->allow_direct_mac' in ntfy
assert 'remote_command_run(command, c->info_enabled, c->allow_direct_mac' in SRC

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "telegram_commands.h"
static const char *msg(char *buf, size_t cap, long long uid, long long chat, long date, const char *text) {
    snprintf(buf, cap, "{\"update_id\":%lld,\"message\":{\"message_id\":1,\"chat\":{\"id\":%lld,\"type\":\"private\"},\"date\":%ld,\"text\":\"%s\"}}", uid, chat, date, text);
    return buf;
}
int main(void) {
    char a[600], b[600], c[600], d[600], all[4096];
    tg_updates_t u;
    const long now = 1800000000;
    snprintf(all, sizeof all, "{\"ok\":true,\"result\":[%s,%s,%s,%s,{\"update_id\":905,\"message\":{\"chat\":{\"id\":42},\"sticker\":{}}}]}",
             msg(a, sizeof a, 901, 42, now - 5, "/wol@MyBot nas"), msg(b, sizeof b, 902, 77, now - 5, "info"),
             msg(c, sizeof c, 903, 42, now - 700, "info"), msg(d, sizeof d, 904, 42, now - 1, "  /info  "));
    tg_updates_parse(all, strlen(all), "42", (uint32_t)now, &u);
    assert(u.valid && u.count == 2 && u.last_update_id == 905 && u.other_chats == 1 && u.stale == 1);
    assert(!strcmp(u.cmd[0].text, "wol nas") && !strcmp(u.cmd[1].text, "info  "));
    /* clock unknown: no age check */
    tg_updates_parse(all, strlen(all), "42", 0, &u);
    assert(u.count == 3 && u.stale == 0);
    /* group chat (negative id) */
    snprintf(all, sizeof all, "{\"ok\":true,\"result\":[%s]}", msg(a, sizeof a, 7, -1001234567890LL, now, "check nas"));
    tg_updates_parse(all, strlen(all), "-1001234567890", (uint32_t)now, &u);
    assert(u.count == 1 && !strcmp(u.cmd[0].text, "check nas"));
    tg_updates_parse(all, strlen(all), "1001234567890", (uint32_t)now, &u);
    assert(u.count == 0 && u.other_chats == 1 && u.last_update_id == 7);
    /* at most five commands */
    strcpy(all, "{\"ok\":true,\"result\":[");
    for (int i = 0; i < 7; i++) { msg(a, sizeof a, 100 + i, 42, now, "info"); strcat(all, a); if (i < 6) strcat(all, ","); }
    strcat(all, "]}");
    tg_updates_parse(all, strlen(all), "42", (uint32_t)now, &u);
    assert(u.count == 5 && u.last_update_id == 106);
    /* malformed answers */
    const char *bad[] = {"{\"ok\":false,\"result\":[]}", "{\"ok\":true}", "{\"ok\":true,\"result\":{}}", "{\"ok\":true,\"result\":[",
                         "{\"ok\":true,\"result\":[{\"update_id\":5,\"message\":{\"chat\":{\"id\":42},\"text\":\"a\\u0000b\"}}]}", "not json"};
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) { tg_updates_parse(bad[i], strlen(bad[i]), "42", 0, &u); assert(!u.valid && u.count == 0); }
    tg_updates_parse("{\"ok\":true,\"result\":[]}", 24, "", 0, &u); assert(!u.valid);   /* no chat configured */
    /* update ids out of range are ignored */
    const char *range = "{\"ok\":true,\"result\":[{\"update_id\":-3},{\"update_id\":1e12},{\"update_id\":9}]}";
    tg_updates_parse(range, strlen(range), "42", 0, &u); assert(u.valid && u.last_update_id == 9);
    /* oversized command text */
    char long_text[200]; memset(long_text, 'x', 150); long_text[150] = 0;
    snprintf(all, sizeof all, "{\"ok\":true,\"result\":[%s]}", msg(a, sizeof a, 11, 42, now, long_text));
    tg_updates_parse(all, strlen(all), "42", (uint32_t)now, &u); assert(u.count == 0 && u.last_update_id == 11);
    /* normalize */
    char out[TG_CMD_TEXT_MAX];
    assert(tg_command_normalize("/wol@Mattboxx_bot pc studio", out, sizeof out) && !strcmp(out, "wol pc studio"));
    assert(tg_command_normalize("/info", out, sizeof out) && !strcmp(out, "info"));
    assert(tg_command_normalize("wol aa:bb:cc:dd:ee:ff", out, sizeof out) && !strcmp(out, "wol aa:bb:cc:dd:ee:ff"));
    assert(!tg_command_normalize("/", out, sizeof out) && !tg_command_normalize("@bot", out, sizeof out));
    assert(!tg_command_normalize("info", out, 4));
    /* poll interval */
    telegram_commands_config_t cfg = {0};
    cfg.poll_interval_seconds = 4; assert(!telegram_commands_config_valid(&cfg));
    cfg.poll_interval_seconds = 5; assert(telegram_commands_config_valid(&cfg));
    cfg.poll_interval_seconds = 300; assert(telegram_commands_config_valid(&cfg));
    cfg.poll_interval_seconds = 301; assert(!telegram_commands_config_valid(&cfg));
    assert(!telegram_commands_config_valid(NULL));
    puts("telegram commands ok");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='tg-cmd-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-DTG_COMMANDS_HOST_TEST', '-I', str(path), '-I', str(ROOT / 'main')]
        libs = []
        dep = os.environ.get('CJSON_SOURCE', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/json/cJSON/cJSON.c'))
        if Path(dep).exists():
            flags += ['-I', str(Path(dep).parent)]
            sources = [dep]
        else:
            flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
            libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
            sources = []
        if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        cc = os.environ.get('CC', 'gcc')
        objs = []
        for i, s in enumerate(sources):
            o = path / f'dep{i}.o'
            subprocess.run([cc, '-std=gnu11', '-O1', '-w', '-c', s, '-o', str(o)], check=True)
            objs.append(str(o))
        subprocess.run([cc, *flags, str(path / 'test.c'), str(ROOT / 'main/telegram_commands.c'), *objs, '-o', str(exe), *libs], check=True)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        assert out.returncode == 0 and 'telegram commands ok' in out.stdout, (out.returncode, out.stdout, out.stderr)
    print('telegram commands: chat authorization, age limit, batch cap, malformed answers, /cmd@Bot forms; '
          'backlog skipped, offset before running, no flash writes, shared command engine with ntfy')


if __name__ == '__main__':
    main()
