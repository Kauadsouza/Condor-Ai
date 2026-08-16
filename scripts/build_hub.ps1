$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HubRoot = if ($env:CONDOR_HUB_SOURCE) { $env:CONDOR_HUB_SOURCE } else {
    Join-Path (Split-Path -Parent (Split-Path -Parent $ProjectRoot)) "ARTX Hub"
}
if (-not (Test-Path -LiteralPath (Join-Path $HubRoot "package.json"))) {
    throw "ARTX Hub nao encontrado em $HubRoot. Defina CONDOR_HUB_SOURCE se necessario."
}
Push-Location $HubRoot
$PreviousLocalBuild = $env:CONDOR_LOCAL_BUILD
try {
    $env:CONDOR_LOCAL_BUILD = "1"
    npm.cmd install
    npm.cmd run build
} finally {
    if ($null -eq $PreviousLocalBuild) {
        Remove-Item Env:CONDOR_LOCAL_BUILD -ErrorAction SilentlyContinue
    } else {
        $env:CONDOR_LOCAL_BUILD = $PreviousLocalBuild
    }
    Pop-Location
}
Write-Host "ARTX Command Center pronto em $HubRoot\out" -ForegroundColor Green
