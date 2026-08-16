$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OllamaExe = Join-Path $ProjectRoot "runtime\ollama\windows\ollama.exe"
if (-not (Test-Path -LiteralPath $OllamaExe)) {
    throw "Execute scripts\install_local_ai.ps1 primeiro."
}
$env:OLLAMA_HOST = "127.0.0.1:11434"
& $OllamaExe pull "qwen3:4b-instruct"
& $OllamaExe pull "qwen3-vl:2b"
