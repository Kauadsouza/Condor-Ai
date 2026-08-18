$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$InstallScript = Join-Path $PSScriptRoot "install.ps1"
$InstallAiScript = Join-Path $PSScriptRoot "install_local_ai.ps1"
$InstallArduinoScript = Join-Path $PSScriptRoot "install_arduino_cli.ps1"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OllamaExe = Join-Path $ProjectRoot "runtime\ollama\windows\ollama.exe"
$StateRoot = if ($env:CONDOR_HOME) {
    [IO.Path]::GetFullPath($env:CONDOR_HOME)
} else {
    Join-Path ([Environment]::GetFolderPath("UserProfile")) ".condor"
}

function Test-CondorPort([int]$Port) {
    $Client = [Net.Sockets.TcpClient]::new()
    try {
        $Result = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
        return $Result.AsyncWaitHandle.WaitOne(400) -and $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

Write-Host "[1/5] Instalando Condor, voz local e atalho..." -ForegroundColor Cyan
& $InstallScript

Write-Host "[2/5] Instalando o runtime local de IA..." -ForegroundColor Cyan
& $InstallAiScript

Write-Host "[3/5] Instalando compilador e gravador Arduino..." -ForegroundColor Cyan
& $InstallArduinoScript

$PreviousHost = $env:OLLAMA_HOST
$PreviousModels = $env:OLLAMA_MODELS
$PreviousCloud = $env:OLLAMA_NO_CLOUD
$PreviousHistory = $env:OLLAMA_NOHISTORY
$PreviousContext = $env:OLLAMA_CONTEXT_LENGTH
$StartedOllama = $null

try {
    $env:OLLAMA_HOST = "127.0.0.1:11434"
    $env:OLLAMA_MODELS = Join-Path $StateRoot "models"
    $env:OLLAMA_NO_CLOUD = "1"
    $env:OLLAMA_NOHISTORY = "1"
    $env:OLLAMA_CONTEXT_LENGTH = "32768"

    if (-not (Test-CondorPort 11434)) {
        $StartedOllama = Start-Process -FilePath $OllamaExe -ArgumentList "serve" `
            -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
        for ($Attempt = 0; $Attempt -lt 80 -and -not (Test-CondorPort 11434); $Attempt++) {
            Start-Sleep -Milliseconds 250
        }
        if (-not (Test-CondorPort 11434)) {
            throw "A IA local nao iniciou em 127.0.0.1:11434."
        }
    }

    Write-Host "[4/5] Baixando os modelos locais de conversa e visao..." -ForegroundColor Cyan
    foreach ($Model in @("qwen3:4b-instruct", "qwen3-vl:2b")) {
        & $OllamaExe pull $Model
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao instalar o modelo local $Model."
        }
    }

    Write-Host "[5/5] Executando diagnostico final..." -ForegroundColor Cyan
    & $PythonExe (Join-Path $PSScriptRoot "doctor.py")
    if ($LASTEXITCODE -ne 0) {
        throw "A instalacao terminou, mas o diagnostico encontrou componentes pendentes."
    }
} finally {
    if ($StartedOllama -and -not $StartedOllama.HasExited) {
        Stop-Process -Id $StartedOllama.Id
    }
    if ($null -eq $PreviousHost) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue } else { $env:OLLAMA_HOST = $PreviousHost }
    if ($null -eq $PreviousModels) { Remove-Item Env:OLLAMA_MODELS -ErrorAction SilentlyContinue } else { $env:OLLAMA_MODELS = $PreviousModels }
    if ($null -eq $PreviousCloud) { Remove-Item Env:OLLAMA_NO_CLOUD -ErrorAction SilentlyContinue } else { $env:OLLAMA_NO_CLOUD = $PreviousCloud }
    if ($null -eq $PreviousHistory) { Remove-Item Env:OLLAMA_NOHISTORY -ErrorAction SilentlyContinue } else { $env:OLLAMA_NOHISTORY = $PreviousHistory }
    if ($null -eq $PreviousContext) { Remove-Item Env:OLLAMA_CONTEXT_LENGTH -ErrorAction SilentlyContinue } else { $env:OLLAMA_CONTEXT_LENGTH = $PreviousContext }
}

Write-Host "Condor pronto. Abra o atalho Condor na Area de Trabalho." -ForegroundColor Green
Write-Host "No primeiro acesso, defina sua palavra de acesso. Dados privados nao sao baixados do GitHub." -ForegroundColor Yellow
