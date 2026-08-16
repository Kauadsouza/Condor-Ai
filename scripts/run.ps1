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
    $env:OLLAMA_HOST = "127.0.0.1:11434"
    $env:OLLAMA_MODELS = Join-Path $HOME ".condor\models"
    $env:OLLAMA_NO_CLOUD = "1"
    $env:OLLAMA_NOHISTORY = "1"
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
} finally {
    if ($LocalAiProcess -and -not $LocalAiProcess.HasExited) {
        Stop-Process -Id $LocalAiProcess.Id
    }
}
