$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Execute scripts\install.ps1 primeiro."
}

function Test-CondorLocalPort {
    $Client = [Net.Sockets.TcpClient]::new()
    try {
        $Result = $Client.BeginConnect("127.0.0.1", 11434, $null, $null)
        return $Result.AsyncWaitHandle.WaitOne(300) -and $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

$LocalAiProcess = $null
$OllamaExe = Join-Path $ProjectRoot "runtime\ollama\windows\ollama.exe"
if ((Test-Path -LiteralPath $OllamaExe) -and -not (Test-CondorLocalPort)) {
    $StateRoot = if ($env:CONDOR_HOME) {
        [IO.Path]::GetFullPath($env:CONDOR_HOME)
    } else {
        Join-Path ([Environment]::GetFolderPath("UserProfile")) ".condor"
    }
    $env:OLLAMA_HOST = "127.0.0.1:11434"
    $env:OLLAMA_MODELS = Join-Path $StateRoot "models"
    $env:OLLAMA_NO_CLOUD = "1"
    $env:OLLAMA_NOHISTORY = "1"
    $env:OLLAMA_CONTEXT_LENGTH = "8192"
    # Cache de contexto em 8 bits: metade da memoria de video, mais do modelo
    # cabe na GPU de 4 GB e a resposta sai mais rapido.
    $env:OLLAMA_FLASH_ATTENTION = "1"
    $env:OLLAMA_KV_CACHE_TYPE = "q8_0"
    $LocalAiProcess = Start-Process -FilePath $OllamaExe -ArgumentList "serve" `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    for ($Attempt = 0; $Attempt -lt 80 -and -not (Test-CondorLocalPort); $Attempt++) {
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-CondorLocalPort)) {
        if ($LocalAiProcess -and -not $LocalAiProcess.HasExited) {
            Stop-Process -Id $LocalAiProcess.Id
        }
        throw "A IA local nao iniciou em 127.0.0.1:11434."
    }
}

try {
    & $PythonExe -m condor
    $CondorExitCode = $LASTEXITCODE
} finally {
    if ($LocalAiProcess -and -not $LocalAiProcess.HasExited) {
        Stop-Process -Id $LocalAiProcess.Id
        # Parar o Ollama à força deixa o executor do modelo vivo, segurando a
        # memória da placa de vídeo. Encerra só os desta instalação.
        $Runtime = Join-Path $ProjectRoot "runtime\ollama"
        Get-Process llama-server -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and $_.Path.StartsWith($Runtime, [StringComparison]::OrdinalIgnoreCase) } |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
exit $CondorExitCode
