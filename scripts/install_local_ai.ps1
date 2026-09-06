$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "runtime\ollama\windows"
$OllamaExe = Join-Path $RuntimeRoot "ollama.exe"
$Version = "0.33.3"
$ExpectedSha256 = "52cb36a62e7e501f61514f60212dec7117b6c098811357585e02fffe32d2fcd7"
$DownloadUrl = "https://github.com/ollama/ollama/releases/download/v$Version/ollama-windows-amd64.zip"

function Assert-OllamaRuntimeSignature([string]$Root) {
    $NativeFiles = @(Get-ChildItem -LiteralPath $Root -File -Recurse | Where-Object {
        $_.Extension -in ".exe", ".dll"
    })
    if ($NativeFiles.Count -eq 0) {
        throw "O pacote do Ollama nao contem executaveis nativos."
    }
    foreach ($NativeFile in $NativeFiles) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $NativeFile.FullName
        if ($Signature.Status -ne "Valid") {
            throw "Assinatura Authenticode invalida no pacote do Ollama: $($NativeFile.Name)"
        }
    }
    $OllamaSignature = Get-AuthenticodeSignature -LiteralPath (Join-Path $Root "ollama.exe")
    if ($OllamaSignature.SignerCertificate.Subject -notmatch "O=Ollama Inc\.") {
        throw "O executavel principal nao foi assinado pela Ollama Inc."
    }
}

if (Test-Path -LiteralPath $OllamaExe) {
    Assert-OllamaRuntimeSignature $RuntimeRoot
    Write-Host "Runtime local ja instalado em $RuntimeRoot" -ForegroundColor Green
    exit 0
}

$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("condor-ollama-" + [guid]::NewGuid().ToString("N"))
$Archive = Join-Path $TempRoot "ollama.zip"
$StagingRoot = Join-Path $TempRoot "staging"
New-Item -ItemType Directory -Path $TempRoot | Out-Null
New-Item -ItemType Directory -Path $StagingRoot | Out-Null

try {
    Write-Host "Baixando o runtime local oficial Ollama $Version..."
    Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $Archive
    $ActualSha256 = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Checksum do pacote do Ollama nao confere. Instalacao interrompida."
    }
    Expand-Archive -LiteralPath $Archive -DestinationPath $StagingRoot -Force
    if (-not (Test-Path -LiteralPath (Join-Path $StagingRoot "ollama.exe"))) {
        throw "O arquivo ollama.exe nao apareceu no pacote oficial."
    }
    Assert-OllamaRuntimeSignature $StagingRoot
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    Copy-Item -Path (Join-Path $StagingRoot "*") -Destination $RuntimeRoot -Recurse -Force
    Assert-OllamaRuntimeSignature $RuntimeRoot
    Write-Host "Runtime local instalado em $RuntimeRoot" -ForegroundColor Green
} finally {
    $ResolvedTemp = [IO.Path]::GetFullPath($TempRoot)
    $SystemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($ResolvedTemp.StartsWith($SystemTemp) -and [IO.Directory]::Exists($ResolvedTemp)) {
        [IO.Directory]::Delete($ResolvedTemp, $true)
    }
}
