$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $ProjectRoot "Condor.exe"
$IconPath = Join-Path $ProjectRoot "condor\ui\assets\condor-logo.ico"
$IdentitySource = Join-Path $ProjectRoot "windows\ShortcutIdentity.cs"
$AppId = "ARTX.Condor.Local"

& (Join-Path $PSScriptRoot "build_windows_launcher.ps1")
if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "O inicializador nativo do Condor nao foi encontrado."
}
if (-not (Test-Path -LiteralPath $IconPath)) {
    throw "A logo universal do Condor nao foi encontrada."
}
if (-not (Test-Path -LiteralPath $IdentitySource)) {
    throw "O componente de identidade do atalho nao foi encontrado."
}

if (-not ("Condor.Windows.ShortcutIdentity" -as [type])) {
    Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath $IdentitySource) -Language CSharp
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = [Environment]::GetFolderPath("Programs")
$Shell = New-Object -ComObject WScript.Shell

function New-CondorShortcut([string]$ShortcutPath) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.Arguments = ""
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "Condor - sistema local privado"
    $Shortcut.IconLocation = "$IconPath,0"
    $Shortcut.Save()
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($Shortcut) | Out-Null
    [Condor.Windows.ShortcutIdentity]::Apply($ShortcutPath, $AppId)
}

$DesktopShortcut = Join-Path $Desktop "Condor.lnk"
$StartMenuShortcut = Join-Path $StartMenu "Condor.lnk"
New-CondorShortcut $DesktopShortcut
New-CondorShortcut $StartMenuShortcut

Write-Host "Aplicativo Condor criado na Area de Trabalho e no Menu Iniciar." -ForegroundColor Green
