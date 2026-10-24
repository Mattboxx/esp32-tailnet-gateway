"""Actual layout-migration core of main/layout_migration.c, no flash access.

Uses the real 3.x and 2.x partition tables (generated from partitions.csv and
partitions-2x.csv by ESP-IDF's gen_esp32part.py), a real ESP32-S3 bootloader
header and app descriptor layout, otadata entries checked against the CRC
otatool computes, and GitHub release selection with cJSON. Flash writes,
HTTP and the bridge on hardware are NOT covered here.
MIG_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import binascii
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/layout_migration.c').read_text(encoding='utf-8')
header = (ROOT / 'main/layout_migration.h').read_text(encoding='utf-8')
core = source.split('/* --- migration core (begin) --- */', 1)[1].split('/* --- migration core (end) --- */', 1)[0]
types = 'typedef struct {char name[17];' + header.split('typedef struct {char name[17];', 1)[1].split('/* Core (pure, host-tested). */', 1)[0]
idf = Path(os.environ.get('IDF_PATH', Path.home() / '.platformio/packages/framework-espidf'))
gen = idf / 'components/partition_table/gen_esp32part.py'


def table(csv, size):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / 't.bin'
        subprocess.run([sys.executable, str(gen), '--flash-size', size, str(ROOT / csv), str(out)], check=True,
                       capture_output=True)
        return out.read_bytes()


def c_array(name, data):
    return f'static const uint8_t {name}[{len(data)}]={{' + ','.join(str(b) for b in data) + '};\n'


v3 = table('partitions.csv', '8MB')
v2 = table('partitions-2x.csv', '4MB')
# Synthetic ESP32-S3 bootloader header (layout of esp_image_header_t) and an
# app prefix with an esp_app_desc_t: no real firmware is needed for the checks.
boot = bytearray(0x4000)
boot[0], boot[1], boot[2], boot[3] = 0xE9, 3, 2, 0x3F   # magic, 3 segments, DIO, 8 MB | 80 MHz
boot[12:14] = (9).to_bytes(2, 'little')                 # ESP_CHIP_ID_ESP32S3


def app(version, project='esp32_tsr', chip=9):
    image = bytearray(0x200)
    image[0], image[1] = 0xE9, 5
    image[12:14] = chip.to_bytes(2, 'little')
    desc = 32
    image[desc:desc + 4] = (0xABCD5432).to_bytes(4, 'little')
    image[desc + 16:desc + 16 + len(version)] = version.encode()
    image[desc + 48:desc + 48 + len(project)] = project.encode()
    return bytes(image)


def entry(seq, state):
    e = struct.pack('<I', seq) + b'\xff' * 20 + struct.pack('<I', state)
    return e + struct.pack('<I', binascii.crc32(struct.pack('<I', seq), 0xFFFFFFFF) & 0xFFFFFFFF)


expected_first, expected_second = entry(2, 0), entry(1, 2)

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cJSON.h"
#include "ota_validation.h"
''' + types + core + c_array('V3', v3) + c_array('V2', v2) + c_array('BOOT', boot) \
    + c_array('APP3', app('3.0.0-dev.2')) + c_array('APP2', app('2.1.0')) + c_array('APPOTHER', app('3.0.0', 'other_app')) \
    + c_array('APPCHIP', app('3.0.0', chip=0)) + c_array('FIRST', expected_first) + c_array('SECOND', expected_second) + r'''
static void row(cJSON *rows,const char *tag,bool pre,bool draft,const char *skip,unsigned firmware){
    static const char *names[3]=MIG_ASSETS;unsigned sizes[3]={firmware,0x4000,3072};
    cJSON *r=cJSON_CreateObject(),*assets=cJSON_AddArrayToObject(r,"assets");
    cJSON_AddStringToObject(r,"tag_name",tag);cJSON_AddBoolToObject(r,"prerelease",pre);cJSON_AddBoolToObject(r,"draft",draft);
    for(int i=0;i<3;i++){if(skip&&!strcmp(skip,names[i]))continue;cJSON *a=cJSON_CreateObject();
        cJSON_AddStringToObject(a,"name",names[i]);cJSON_AddStringToObject(a,"state","uploaded");cJSON_AddNumberToObject(a,"size",sizes[i]);
        cJSON_AddStringToObject(a,"digest","sha256:1111111111111111111111111111111111111111111111111111111111111111");cJSON_AddItemToArray(assets,a);}
    cJSON_AddItemToArray(rows,r);
}
int main(void){
    mig_part_t parts[12];int md5=-1;
    int n=mig_parse_table(V3,sizeof V3,parts,12,&md5);
    assert(n==7&&md5==7&&mig_layout_kind(parts,n)==MIG_LAYOUT_V3&&!strcmp(parts[6].name,"storage")&&parts[4].offset==0x3A0000);
    n=mig_parse_table(V2,sizeof V2,parts,12,&md5);
    assert(n==6&&md5==6&&mig_layout_kind(parts,n)==MIG_LAYOUT_V2&&parts[4].offset==0x200000&&parts[4].size==0x1E0000);
    /* Any change of a field is an unknown layout: never rewrite from a guess. */
    uint8_t t[sizeof V3];
    for(unsigned field=0;field<4;field++){memcpy(t,V3,sizeof t);
        if(field==0)t[2+32*3]^=1;           /* type of ota_0 */
        if(field==1)t[4+32*4]^=0x10;        /* offset of ota_1 */
        if(field==2)t[8+32*6]^=1;           /* size of storage */
        if(field==3)t[12]^='X';             /* label of nvs */
        int m=mig_parse_table(t,sizeof t,parts,12,&md5);assert(m<0||mig_layout_kind(parts,m)==MIG_LAYOUT_UNKNOWN);}
    memcpy(t,V3,sizeof t);memset(t+32*7,0x00,32);assert(mig_parse_table(t,sizeof t,parts,12,&md5)<0);   /* garbage terminator */
    assert(mig_parse_table(V3,sizeof V3,parts,6,&md5)<0);                                             /* more entries than room */
    assert(mig_parse_table(V3,7*32,parts,12,&md5)<0);                                                 /* truncated */
    memcpy(t,V3,sizeof t);memset(t+12,'A',16);assert(mig_parse_table(t,sizeof t,parts,12,&md5)<0);      /* unterminated label */
    assert(mig_parse_table(NULL,0,parts,12,&md5)<0);
    /* Bootloader: ESP32-S3, 8 MB header, ends before the partition table. */
    uint8_t b[sizeof BOOT];memcpy(b,BOOT,sizeof b);assert(mig_bootloader_ok(b,sizeof b));
    b[3]=0x2F;assert(!mig_bootloader_ok(b,sizeof b));b[3]=0x4F;assert(!mig_bootloader_ok(b,sizeof b));b[3]=0x3F;   /* 4 or 16 MB */
    b[12]=0;assert(!mig_bootloader_ok(b,sizeof b));b[12]=9;b[0]=0;assert(!mig_bootloader_ok(b,sizeof b));b[0]=0xE9;
    assert(!mig_bootloader_ok(b,0x8001)&&!mig_bootloader_ok(b,0xFFF)&&!mig_bootloader_ok(NULL,0x4000));
    /* App: same project, version equal to the release tag, major >= 3. */
    assert(mig_app_ok(APP3,sizeof APP3,"esp32_tsr","v3.0.0-dev.2")&&mig_app_ok(APP3,sizeof APP3,"esp32_tsr","3.0.0-dev.2"));
    assert(!mig_app_ok(APP3,sizeof APP3,"esp32_tsr","v3.0.0")&&!mig_app_ok(APP2,sizeof APP2,"esp32_tsr","v2.1.0"));
    assert(!mig_app_ok(APPOTHER,sizeof APPOTHER,"esp32_tsr","v3.0.0")&&!mig_app_ok(APPCHIP,sizeof APPCHIP,"esp32_tsr","v3.0.0"));
    assert(!mig_app_ok(APP3,60,"esp32_tsr","v3.0.0-dev.2"));
    /* otadata: byte-identical to what otatool computes. */
    uint8_t first[32],second[32];mig_otadata(first,second);
    assert(!memcmp(first,FIRST,32)&&!memcmp(second,SECOND,32));
    /* Release choice: newest 3.x with all three assets on the channel. */
    cJSON *rows=cJSON_CreateArray();mig_target_t target;
    row(rows,"v2.1.0",false,false,NULL,0x100000);
    assert(!mig_pick_release(rows,true,&target));                        /* 2.x is never a target */
    row(rows,"v3.0.0",false,false,NULL,0x200000);
    row(rows,"v3.1.0-beta.1",true,false,NULL,0x200000);
    row(rows,"v3.2.0",false,false,"partitions.bin",0x200000);           /* incomplete */
    row(rows,"v3.3.0",false,false,NULL,0x380001);                       /* does not fit the slot */
    row(rows,"v3.4.0",false,true,NULL,0x200000);                        /* draft */
    row(rows,"v3.5.0-beta.1",false,false,NULL,0x200000);                /* beta not marked pre-release */
    assert(mig_pick_release(rows,false,&target)&&!strcmp(target.tag,"v3.0.0")&&target.size[0]==0x200000&&target.size[2]==3072&&target.digest[1][0]==0x11);
    assert(mig_pick_release(rows,true,&target)&&!strcmp(target.tag,"v3.1.0-beta.1"));
    assert(!mig_pick_release(NULL,true,&target));
    cJSON_Delete(rows);
    puts("PASS: actual migration core: real 2.x/3.x tables (exact layouts, MD5 position, malformed refused), bootloader/app checks, otadata equal to otatool, release choice (fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='migration-') as folder:
    path = Path(folder); (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(ROOT / 'main')]
    libs = []
    dep = os.environ.get('CJSON_SOURCE')
    if dep: flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('MIG_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
