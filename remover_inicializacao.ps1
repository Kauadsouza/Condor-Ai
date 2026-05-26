# ============================================================
#  CONDOR - Remover da inicializacao automatica do Windows
# ============================================================

$regKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
$name   = "CondorAI"

Write-Host ""
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "  CONDOR - Removendo da Inicializacao" -ForegroundColor Cyan
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host ""

# Remove registro de startup
$existing = Get-ItemProperty -Path $regKey -Name $name -ErrorAction SilentlyContinue
if ($existing) {
    Remove-ItemProperty -Path $regKey -Name $name
    Write-Host "  OK! Condor removido da inicializacao do Windows." -ForegroundColor Green
} else {
    Write-Host "  Condor nao estava registrado na inicializacao." -ForegroundColor Yellow
}

# Encerra processos do launcher
$procs = Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*condor_launcher*"
}
if ($procs) {
    Write-Host ""
    Write-Host "  Encerrando launcher..." -ForegroundColor Yellow
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  Encerrado: PID $($p.ProcessId)" -ForegroundColor DarkGray
    }
}

# Encerra o servidor FastAPI se estiver rodando
$serverProcs = Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*-m condor*"
}
foreach ($p in $serverProcs) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "  Servidor encerrado: PID $($p.ProcessId)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Feito. Condor nao iniciara mais automaticamente." -ForegroundColor Green
Write-Host ""
