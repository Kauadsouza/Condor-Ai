$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OllamaExe = Join-Path $ProjectRoot "runtime\ollama\windows\ollama.exe"
if (-not (Test-Path -LiteralPath $OllamaExe)) {
    throw "Execute scripts\install_local_ai.ps1 primeiro."
}
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_MODELS = Join-Path $HOME ".condor\models"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NOHISTORY = "1"
& $OllamaExe serve
