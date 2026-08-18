$ErrorActionPreference = "Stop"
$Version = "1.5.1"
$ExpectedSha256 = "fabe42e0eb04d00e776a66178299ff95a46c623dbc260f997e58fd514853dd40"
$StateRoot = if ($env:CONDOR_HOME) {
    [IO.Path]::GetFullPath($env:CONDOR_HOME)
} else {
    Join-Path ([Environment]::GetFolderPath("UserProfile")) ".condor"
}
$ToolRoot = Join-Path $StateRoot "tools\arduino-cli"
$ArduinoCli = Join-Path $ToolRoot "arduino-cli.exe"
$Archive = Join-Path ([IO.Path]::GetTempPath()) "condor-arduino-cli-$Version-$PID.zip"
$DownloadUrl = "https://github.com/arduino/arduino-cli/releases/download/v$Version/arduino-cli_${Version}_Windows_64bit.zip"

try {
    New-Item -ItemType Directory -Path $ToolRoot -Force | Out-Null
    Write-Host "Baixando Arduino CLI $Version da release oficial..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Archive -UseBasicParsing
    $ActualSha256 = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Checksum do Arduino CLI nao confere. Instalacao interrompida."
    }
    Expand-Archive -LiteralPath $Archive -DestinationPath $ToolRoot -Force
    if (-not (Test-Path -LiteralPath $ArduinoCli -PathType Leaf)) {
        throw "arduino-cli.exe nao foi encontrado depois da extracao."
    }
    & $ArduinoCli core update-index
    if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar o indice de placas Arduino." }
    & $ArduinoCli core install "arduino:avr@1.8.8"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o suporte Arduino AVR 1.8.8." }
    & $ArduinoCli version
    Write-Host "Arduino CLI e placas AVR prontos para o Condor." -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $Archive -PathType Leaf) {
        Remove-Item -LiteralPath $Archive -Force
    }
}
