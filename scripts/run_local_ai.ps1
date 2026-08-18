$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OllamaExe = Join-Path $ProjectRoot "runtime\ollama\windows\ollama.exe"
if (-not (Test-Path -LiteralPath $OllamaExe)) {
    throw "Execute scripts\install_local_ai.ps1 primeiro."
}
$env:OLLAMA_HOST = "127.0.0.1:11434"
$StateRoot = if ($env:CONDOR_HOME) {
    [IO.Path]::GetFullPath($env:CONDOR_HOME)
} else {
    Join-Path ([Environment]::GetFolderPath("UserProfile")) ".condor"
}
$env:OLLAMA_MODELS = Join-Path $StateRoot "models"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NOHISTORY = "1"
$env:OLLAMA_CONTEXT_LENGTH = "32768"
& $OllamaExe serve
