$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "runtime\ollama\windows"
$OllamaExe = Join-Path $RuntimeRoot "ollama.exe"
$DownloadUrl = "https://ollama.com/download/ollama-windows-amd64.zip"

if (Test-Path -LiteralPath $OllamaExe) {
    Write-Host "Runtime local ja instalado em $RuntimeRoot" -ForegroundColor Green
    exit 0
}

$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("condor-ollama-" + [guid]::NewGuid().ToString("N"))
$Archive = Join-Path $TempRoot "ollama.zip"
New-Item -ItemType Directory -Path $TempRoot | Out-Null
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null

try {
    Write-Host "Baixando o runtime local oficial..."
    Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $Archive
    Expand-Archive -LiteralPath $Archive -DestinationPath $RuntimeRoot -Force
    if (-not (Test-Path -LiteralPath $OllamaExe)) {
        throw "O arquivo ollama.exe nao apareceu no pacote oficial."
    }
    Write-Host "Runtime local instalado em $RuntimeRoot" -ForegroundColor Green
} finally {
    $ResolvedTemp = [IO.Path]::GetFullPath($TempRoot)
    $SystemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($ResolvedTemp.StartsWith($SystemTemp) -and [IO.Directory]::Exists($ResolvedTemp)) {
        [IO.Directory]::Delete($ResolvedTemp, $true)
    }
}
