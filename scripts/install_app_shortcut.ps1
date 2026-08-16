$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$AppEntry = Join-Path $ProjectRoot "condor_app.pyw"
$IconPath = Join-Path $ProjectRoot "condor\ui\assets\condor-logo.ico"

if (-not (Test-Path -LiteralPath $Pythonw)) {
    throw "Execute scripts\install.ps1 antes de criar o atalho."
}
if (-not (Test-Path -LiteralPath $AppEntry)) {
    throw "O inicializador visual do Condor nao foi encontrado."
}
if (-not (Test-Path -LiteralPath $IconPath)) {
    throw "A logo universal do Condor nao foi encontrada."
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Condor.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = "`"$AppEntry`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Condor - sistema local privado"
$Shortcut.IconLocation = "$IconPath,0"
$Shortcut.Save()

Write-Host "Aplicativo Condor criado em $ShortcutPath" -ForegroundColor Green
