$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot ".venv"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 ou superior nao foi encontrado no PATH."
}

$PythonVersionText = python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ($LASTEXITCODE -ne 0) {
    throw "O comando python existe, mas nao foi possivel executa-lo."
}
$PythonVersion = [version]$PythonVersionText.Trim()
if ($PythonVersion -lt [version]"3.11") {
    throw "Python 3.11 ou superior e obrigatorio. Versao encontrada: $PythonVersion"
}

python -m venv $VenvPath
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -e $ProjectRoot
& $PythonExe "$ProjectRoot\scripts\install_voice_models.py"
& $PythonExe "$ProjectRoot\testes\rodar_testes.py"
& "$ProjectRoot\scripts\install_app_shortcut.ps1"
Write-Host "Condor instalado no ambiente privado $VenvPath" -ForegroundColor Green
