# ============================================================
#  CONDOR - Instalar inicializacao automatica com o Windows
# ============================================================

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
$launcher = Join-Path $ROOT "condor_launcher.pyw"

Write-Host ""
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "  CONDOR - Instalador de Inicializacao" -ForegroundColor Cyan
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $launcher)) {
    Write-Host "  ERRO: condor_launcher.pyw nao encontrado em:" -ForegroundColor Red
    Write-Host "  $ROOT" -ForegroundColor Red
    exit 1
}

# Localiza o Python instalado no sistema
function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        $p = $null
        try { $p = (Get-Command $cmd -ErrorAction Stop).Source } catch {}
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host "  ERRO: Python nao encontrado no PATH." -ForegroundColor Red
    Write-Host "  Instale o Python e adicione ao PATH antes de continuar." -ForegroundColor Red
    exit 1
}

Write-Host "  Python encontrado: $python" -ForegroundColor Gray

# Verifica se faster-whisper e sounddevice estao instalados
$checkLibs = & $python -c "import faster_whisper, sounddevice; print('ok')" 2>&1
if ($checkLibs -ne "ok") {
    Write-Host ""
    Write-Host "  AVISO: faster-whisper ou sounddevice nao instalados." -ForegroundColor Yellow
    Write-Host "  A escuta de wake word nao funcionara sem eles." -ForegroundColor Yellow
    Write-Host "  Instale com: pip install faster-whisper sounddevice" -ForegroundColor Yellow
    Write-Host ""
}

# Prefere pythonw.exe (sem janela de console)
$pyDir   = Split-Path $python
$pythonw = Join-Path $pyDir "pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Host "  Aviso: pythonw.exe nao encontrado, usando python.exe" -ForegroundColor Yellow
    $pythonw = $python
}

# Registra no startup do Windows (HKCU - sem precisar de admin)
$regKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
$cmd    = "`"$pythonw`" `"$launcher`""

Set-ItemProperty -Path $regKey -Name "CondorAI" -Value $cmd

Write-Host ""
Write-Host "  OK! Registro salvo em:" -ForegroundColor Green
Write-Host "  HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\CondorAI" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Comando: $cmd" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Condor vai iniciar automaticamente no proximo login!" -ForegroundColor Green
Write-Host ""

# Mata instancias antigas do launcher se existirem
Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*condor_launcher*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Inicia agora
Write-Host "  Iniciando Condor em background..." -ForegroundColor Yellow
Start-Process -FilePath $pythonw -ArgumentList "`"$launcher`"" -WindowStyle Hidden
Write-Host ""
Write-Host "  Condor rodando em background!" -ForegroundColor Green
Write-Host ""
Write-Host "  Fale 'condor na escuta' para abrir a interface." -ForegroundColor Cyan
Write-Host "  Log em: $ROOT\data\launcher.log" -ForegroundColor DarkGray
Write-Host ""
