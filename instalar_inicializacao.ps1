# ═══════════════════════════════════════════════════════════════════
#  CONDOR — subir junto com o Windows
#
#  Cria um atalho na pasta de Inicializacao apontando pro launcher.
#  Como o launcher e .pyw rodado pelo pythonw.exe, nada aparece na tela.
#
#  Uso:  botao direito neste arquivo > Executar com PowerShell
#  Desfazer:  remover_inicializacao.ps1
# ═══════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

$raiz     = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $raiz "condor_launcher.pyw"

if (-not (Test-Path $launcher)) {
    Write-Host "Nao achei o condor_launcher.pyw em $raiz" -ForegroundColor Red
    exit 1
}

# Acha o pythonw.exe (o Python sem console) do mesmo Python que voce usa
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "Python nao esta no PATH. Instale o Python e tente de novo." -ForegroundColor Red
    exit 1
}
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$inicializacao = [Environment]::GetFolderPath("Startup")
$atalho        = Join-Path $inicializacao "Condor.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk   = $shell.CreateShortcut($atalho)
$lnk.TargetPath       = $pythonw
$lnk.Arguments        = "`"$launcher`""
$lnk.WorkingDirectory = $raiz
$lnk.WindowStyle      = 7           # minimizado, sem foco
$lnk.Description      = "CONDOR - assistente pessoal"
$lnk.Save()

Write-Host ""
Write-Host "  Pronto. O Condor sobe sozinho quando voce ligar o PC." -ForegroundColor Green
Write-Host "  Atalho: $atalho"
Write-Host "  Rodando com: $pythonw"
Write-Host ""
Write-Host "  Pra ligar agora sem reiniciar:" -ForegroundColor Cyan
Write-Host "     Start-Process '$pythonw' -ArgumentList '`"$launcher`"'"
Write-Host ""
