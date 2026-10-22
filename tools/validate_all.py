"""Explicit consolidated OFFLINE validation; never imports/runs device tests.
Complete logs remain under ignored build/validation-*/. No flash/push/release.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DRIVERS='release_packaging device_session feature_preservation upstream_033 upstream_038 ntfy_stack ntfy_logic ntfy_transport ntfy_stream snmp_codec route_hook netif_hooks runtime_recovery portmap forwarding_transactions web_port tailnet_filter tailnet_state tailnet_api tailnet_core tailnet_sdk peer_dns ota_remote gateway_operations tailnet_authorization peer_convergence policy_protocols policy_reassembly ops_core ops_api service_lease health_monitor development_plan candidate_observer'.split()
DRIVERS+=['json_guard','service_transfer','service_retry','capabilities','mqtt_discovery','web_security','config_profiles','service_check','mqtt_state','eth_uplink','mqtt_commands']
SANITIZERS='UPSTREAM NTFY SNMP ROUTE NETIF RUNTIME PORTMAP FORWARDING WEB_PORT TAILNET PEER_DNS OTA GATEWAY POLICY OPS LEASE HEALTH JSON TRANSFER RETRY CAP DISCOVERY WEB PROFILE SC MQTTSTATE ETH MQTTCMD'.split()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--sanitizers',action='store_true')
    parser.add_argument('--only',help='Comma-separated driver stems, for targeted reruns')
    args=parser.parse_args()
    folder=ROOT/'build'/('validation-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));folder.mkdir(parents=True)
    env=os.environ.copy();sdk=Path.home()/'.platformio/packages/framework-espidf@3.50503.0/components'
    if sdk.is_dir():
        env.setdefault('CJSON_SOURCE',str(sdk/'json/cJSON/cJSON.c'))
        env.setdefault('LWIP_SOURCE',str(sdk/'lwip/lwip'))
    if args.sanitizers:
        if os.name=='nt':parser.error('Use Linux ASan/UBSan; do not mark unavailable Windows sanitizers as passed')
        for prefix in SANITIZERS:env[prefix+'_SANITIZE']='1'
        env.setdefault('ASAN_OPTIONS','detect_leaks=1:halt_on_error=1');env.setdefault('UBSAN_OPTIONS','halt_on_error=1')
    results=[]
    def run(name,command,timeout=300):
        logfile=folder/(name+'.log')
        try:
            with logfile.open('w',encoding='utf-8') as log:
                options={'start_new_session':True} if os.name!='nt' else {
                    'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW}
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,**options)
                try:code=process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Terminate only this runner's freshly created process tree.
                    if process.poll() is None:
                        if os.name=='nt':
                            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT,timeout=15)
                        else:os.killpg(process.pid,signal.SIGKILL)
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill()
                    log.write('\nFAIL: validation timed out; owned test process tree stopped.\n')
                    code=1
            state='PASS' if code==0 else 'FAIL'
        except (OSError,subprocess.TimeoutExpired):state='FAIL'
        results.append(dict(name=name,status=state,log=logfile.name));print(state,name,flush=True)
        if state=='FAIL' and logfile.is_file():
            lines=logfile.read_text(encoding='utf-8',errors='replace').splitlines()
            important=[line for line in lines if 'error:' in line or 'AssertionError' in line or 'FAILED' in line]
            for line in (important[-4:] if important else lines[-4:]):print(line[:400],flush=True)
    if args.build:
        pio=shutil.which('platformio') or str(Path.home()/'.platformio/penv/Scripts/platformio.exe')
        env.setdefault('PLATFORMIO_BUILD_DIR',str(Path(os.environ.get('TEMP','/tmp'))/'mattboxx-esp32-build-0114'))
        run('firmware-build',[pio,'run','-e','esp32-s3'],900)
    selected=args.only.split(',') if args.only else DRIVERS
    if any(name not in DRIVERS for name in selected):parser.error('Unknown offline driver')
    for name in selected:run(name,[sys.executable,str(ROOT/'tools'/('test_'+name+'.py'))])
    if not args.only:
        for name in ('sensitive_scanner','upstream_integration'):
            run(name,[sys.executable,'-m','unittest','discover','-s','tools','-p','test_'+name+'.py'])
        for name in ('control_validation','upstream_validation'):
            binary=folder/(name+('.exe' if os.name=='nt' else ''))
            flags=['-std=c11','-Wall','-Wextra','-Werror','-g']
            if args.sanitizers:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            run(name+'-compile',['gcc',*flags,str(ROOT/'tools'/('test_'+name+'.c')),'-o',str(binary)])
            if results[-1]['status']=='PASS':run(name,[str(binary)])
        run('site-build',[sys.executable,'tools/build_site.py','--check'])
        run('sensitive-history',[sys.executable,'tools/check_sensitive_data.py','--history'])
        run('sensitive-dependency',[sys.executable,'tools/check_sensitive_data.py','--repository','external/microlink'])
    if args.browser:
        runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
        if runtime.is_dir():env.setdefault('NODE_PATH',str(runtime))
        run('browser',['node','tools/test_automation_ui.cjs'])
        run('site-browser',['node','tools/test_site_browser.cjs'],600)
        run('ui-layout',['node','tools/test_ui_layout.cjs'],1200)
    summary=dict(results=results,build_requested=args.build,browser_requested=args.browser,
                 sanitizers_requested=args.sanitizers,targeted_only=bool(args.only),
                 hardware_executed=False,release_qualified=False)
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    failures=[r['name'] for r in results if r['status']=='FAIL']
    print('FAIL' if failures else 'PASS',str(len(results))+' checks; logs: '+str(folder))
    return bool(failures)

if __name__=='__main__':raise SystemExit(main())
