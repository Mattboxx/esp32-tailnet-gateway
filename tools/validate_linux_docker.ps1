# Repeatable Linux host validation; never maps private device artifacts or host credentials.
param([string]$Only = '')
$ErrorActionPreference = 'Stop'
if ($Only -and $Only -notmatch '^[a-z0-9_]+(,[a-z0-9_]+)*$') { throw 'Invalid offline driver list' }
$qaRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaSdk = Join-Path $env:USERPROFILE '.platformio/packages/framework-espidf@3.50503.0/components'
$qaJson = (Resolve-Path (Join-Path $qaSdk 'json/cJSON')).Path
$qaLwip = (Resolve-Path (Join-Path $qaSdk 'lwip/lwip')).Path
$qaStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$qaOutput = Join-Path $qaRoot "build/linux-validation-$qaStamp"
New-Item -ItemType Directory -Path $qaOutput | Out-Null
$qaName = "tailnet-offline-$qaStamp"
# /work/build shadows the entire host build directory: NVS backups, serial
# logs and private-device/LOCAL-ENV.md are not reachable inside this container.
$qaCommand = @'
set -eu
apt-get update > /work/build/setup.log 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y gcc git python3 python3-venv pkg-config libcjson-dev >> /work/build/setup.log 2>&1
python3 -m venv /tmp/qa-python
/tmp/qa-python/bin/pip install PyYAML==6.0.2 >> /work/build/setup.log 2>&1
git config --global --add safe.directory /work
git config --global --add safe.directory /work/external/microlink
uname -a > /work/build/environment.txt
gcc --version >> /work/build/environment.txt
python3 --version >> /work/build/environment.txt
test ! -e /work/build/private-device/LOCAL-ENV.md
/tmp/qa-python/bin/python tools/validate_all.py --sanitizers __DRIVERS__
'@
$qaCommand = $qaCommand.Replace('__DRIVERS__', $(if ($Only) { "--only $Only" } else { '' }))
& docker run --name $qaName --label 'purpose=tailnet-offline-validation' --cpus 2 --memory 4g --pids-limit 256 `
    --security-opt no-new-privileges `
    --mount "type=bind,source=$qaRoot,target=/work,readonly" `
    --mount "type=bind,source=$qaOutput,target=/work/build" `
    --mount "type=bind,source=$qaJson,target=/deps/cJSON,readonly" `
    --mount "type=bind,source=$qaLwip,target=/deps/lwip,readonly" `
    --workdir /work -e CJSON_SOURCE=/deps/cJSON/cJSON.c -e LWIP_SOURCE=/deps/lwip `
    -e GATEWAY_SANITIZER_NO_PIE=1 ubuntu:24.04 bash -lc $qaCommand *> (Join-Path $qaOutput 'container.log')
$qaExit = $LASTEXITCODE
Get-Content (Join-Path $qaOutput 'container.log') | Where-Object { $_ -match '^(PASS|FAIL|SKIP)' }
Write-Output "Linux validation exit=$qaExit; logs=$qaOutput; container=$qaName"
if ($qaExit -ne 0) { Get-Content (Join-Path $qaOutput 'container.log') -Tail 8 }
exit $qaExit
