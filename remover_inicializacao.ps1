# ═══════════════════════════════════════════════════════════════════
#  CONDOR — parar de subir com o Windows
#
#  Tira o atalho da pasta de Inicializacao e encerra o Condor que estiver
#  rodando agora. Nao apaga nada do projeto nem da memoria.
# ═══════════════════════════════════════════════════════════════════

$atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Condor.lnk"

if (Test-Path $atalho) {
    Remove-Item $atalho -Force
    Write-Host "  Atalho de inicializacao removido." -ForegroundColor Green
} else {
    Write-Host "  Nao havia atalho de inicializacao." -ForegroundColor Yellow
}

$rodando = Get-Process pythonw -ErrorAction SilentlyContinue
if ($rodando) {
    $rodando | Stop-Process -Force
    Write-Host "  Condor encerrado ($($rodando.Count) processo(s))." -ForegroundColor Green
} else {
    Write-Host "  Nada rodando pra encerrar." -ForegroundColor Yellow
}
Write-Host ""
