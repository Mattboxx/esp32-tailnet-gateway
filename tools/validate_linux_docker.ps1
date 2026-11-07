# Repeatable Linux host validation; never maps private device artifacts or host credentials.
param([string]$Only = '')
$ErrorActionPreference = 'Stop'
if ($Only -and $Only -notmatch '^[a-z0-9_]+(,[a-z0-9_]+)*$') { throw 'Invalid offline driver list' }
$qaRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaSdk = Join-Path $env:USERPROFILE '.platformio/packages/framework-espidf@3.50503.0/components'
$qaJson = (Resolve-Path (Join-Path $qaSdk 'json/cJSON')).Path
$qaLwip = (Resolve-Path (Join-Path $qaSdk 'lwip/lwip')).Path
$qaMqtt = (Resolve-Path (Join-Path $qaSdk 'mqtt/esp-mqtt')).Path
$qaMbed = (Resolve-Path (Join-Path $qaSdk 'mbedtls/mbedtls')).Path
$qaStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$qaOutput = Join-Path $qaRoot "build/linux-validation-$qaStamp"
New-Item -ItemType Directory -Path $qaOutput | Out-Null
$qaName = "tailnet-offline-$qaStamp"
# Export only the tested HEAD ancestry, not host credentials, worktree control
# files or unrelated local refs. Linked-worktree .git files contain Windows
# paths which cannot be used inside Linux. Bundles supply portable, disposable
# metadata; the source mount stays read-only and includes current dirty files.
$qaBranch = (& git -C $qaRoot symbolic-ref --short HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Validation requires a named root branch' }
$qaMicroRoot = Join-Path $qaRoot 'external/microlink'
$qaMicroBranch = (& git -C $qaMicroRoot symbolic-ref --short HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Validation requires a named MicroLink branch' }
& git -C $qaRoot bundle create (Join-Path $qaOutput 'root.bundle') HEAD "refs/heads/$qaBranch"
if ($LASTEXITCODE -ne 0) { throw 'Root validation bundle failed' }
& git -C $qaMicroRoot bundle create (Join-Path $qaOutput 'microlink.bundle') HEAD "refs/heads/$qaMicroBranch"
if ($LASTEXITCODE -ne 0) { throw 'MicroLink validation bundle failed' }
$qaRootMarker = Join-Path $qaOutput 'root.gitfile'
$qaMicroMarker = Join-Path $qaOutput 'microlink.gitfile'
[System.IO.File]::WriteAllText($qaRootMarker, "gitdir: /tmp/qa-root.git`n", [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($qaMicroMarker, "gitdir: /tmp/qa-microlink.git`n", [System.Text.UTF8Encoding]::new($false))
# /work/build shadows the entire host build directory: NVS backups, serial
# logs and private-device/LOCAL-ENV.md are not reachable inside this container.
$qaCommand = @'
set -eu
apt-get update > /work/build/setup.log 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y gcc git python3 python3-venv pkg-config libcjson-dev >> /work/build/setup.log 2>&1
python3 -m venv /tmp/qa-python
/tmp/qa-python/bin/pip install PyYAML==6.0.2 cryptography==44.0.2 >> /work/build/setup.log 2>&1
cd /tmp
git clone --bare --quiet /work/build/root.bundle /tmp/qa-root.git
git --git-dir=/tmp/qa-root.git config core.bare false
git --git-dir=/tmp/qa-root.git config core.worktree /work
git --git-dir=/tmp/qa-root.git read-tree HEAD
git clone --bare --quiet /work/build/microlink.bundle /tmp/qa-microlink.git
git --git-dir=/tmp/qa-microlink.git config core.bare false
git --git-dir=/tmp/qa-microlink.git config core.worktree /work/external/microlink
git --git-dir=/tmp/qa-microlink.git read-tree HEAD
git config --global --add safe.directory /work
git config --global --add safe.directory /work/external/microlink
cd /work
printf '%s\n' 'Git history scope: bundled root/MicroLink HEAD ancestry; host --all scans are separate.' > /work/build/git-scope.txt
uname -a > /work/build/environment.txt
gcc --version >> /work/build/environment.txt
python3 --version >> /work/build/environment.txt
test ! -e /work/build/private-device/LOCAL-ENV.md
/tmp/qa-python/bin/python tools/validate_all.py --sanitizers __DRIVERS__
'@
$qaCommand = $qaCommand.Replace('__DRIVERS__', $(if ($Only) { "--only $Only" } else { '' }))
# Windows checkouts can preserve CRLF inside the here-string. Bash must receive
# LF even when this PowerShell source was checked out with autocrlf enabled.
$qaCommand = $qaCommand.Replace("`r`n", "`n")
& docker run --name $qaName --label 'purpose=tailnet-offline-validation' --cpus 2 --memory 4g --pids-limit 256 `
    --security-opt no-new-privileges `
    --mount "type=bind,source=$qaRoot,target=/work,readonly" `
    --mount "type=bind,source=$qaOutput,target=/work/build" `
    --mount "type=bind,source=$qaRootMarker,target=/work/.git,readonly" `
    --mount "type=bind,source=$qaMicroMarker,target=/work/external/microlink/.git,readonly" `
    --mount "type=bind,source=$qaJson,target=/deps/cJSON,readonly" `
    --mount "type=bind,source=$qaLwip,target=/deps/lwip,readonly" `
    --mount "type=bind,source=$qaMqtt,target=/deps/esp-mqtt,readonly" `
    --mount "type=bind,source=$qaMbed,target=/deps/mbedtls,readonly" `
    --workdir /work -e CJSON_SOURCE=/deps/cJSON/cJSON.c -e LWIP_SOURCE=/deps/lwip `
    -e MQTT_SOURCE=/deps/esp-mqtt/mqtt_client.c -e MBEDTLS_DIR=/deps/mbedtls `
    -e GATEWAY_SANITIZER_NO_PIE=1 ubuntu:24.04 bash -lc $qaCommand *> (Join-Path $qaOutput 'container.log')
$qaExit = $LASTEXITCODE
Get-Content (Join-Path $qaOutput 'container.log') | Where-Object { $_ -match '^(PASS|FAIL|SKIP)' }
Write-Output "Linux validation exit=$qaExit; logs=$qaOutput; container=$qaName"
if ($qaExit -ne 0) { Get-Content (Join-Path $qaOutput 'container.log') -Tail 8 }
exit $qaExit
