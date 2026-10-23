$ErrorActionPreference = 'Stop'
try {
    $root = Split-Path -Parent $PSScriptRoot
    foreach ($entry in Get-Content -LiteralPath (Join-Path $root 'SHA256SUMS.txt')) {
        if ($entry -notmatch '^([0-9a-f]{64})  ([A-Za-z0-9_./-]+)$') { throw 'Invalid checksum manifest.' }
        $expectedHash = $Matches[1]
        $artifactName = $Matches[2]
        if ($artifactName.Contains('..')) { throw 'Invalid path in checksum manifest.' }
        $actualHash = (Get-FileHash -LiteralPath (Join-Path $root $artifactName) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) { throw "Checksum mismatch: $artifactName. Download the package again." }
    }
    Write-Host 'Package checksums verified.'
} catch {
    Write-Error $_
    exit 1
}
