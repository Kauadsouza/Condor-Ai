$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $ProjectRoot "Condor.exe"
$IconPath = Join-Path $ProjectRoot "condor\ui\assets\condor-logo.ico"
$IdentitySource = Join-Path $ProjectRoot "windows\ShortcutIdentity.cs"
$AppId = "ARTX.Condor.Local"
$Startup = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $Startup "Condor Local.lnk"

foreach ($Required in @($Launcher, $IconPath, $IdentitySource)) {
    if (-not (Test-Path -LiteralPath $Required)) {
        throw "Componente necessario para a inicializacao silenciosa nao encontrado: $Required"
    }
}

if (-not ("Condor.Windows.ShortcutIdentity" -as [type])) {
    Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath $IdentitySource) -Language CSharp
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Launcher
$Shortcut.Arguments = ""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Condor - inicializacao local sem console"
$Shortcut.IconLocation = "$IconPath,0"
$Shortcut.WindowStyle = 1
$Shortcut.Save()
[Runtime.InteropServices.Marshal]::FinalReleaseComObject($Shortcut) | Out-Null
[Condor.Windows.ShortcutIdentity]::Apply($ShortcutPath, $AppId)

Write-Host "Inicializacao silenciosa do Condor instalada em $ShortcutPath" -ForegroundColor Green
