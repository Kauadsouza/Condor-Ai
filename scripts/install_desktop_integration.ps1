param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$CondorRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$CondorLauncher = Join-Path $CondorRoot 'Condor.exe'
$CondorRunner = Join-Path $PSScriptRoot 'run.ps1'
$CondorProtocol = 'HKCU:\Software\Classes\condor'
$CondorTask = 'Condor Local Assistant'
$CondorLegacyStartup = Join-Path ([Environment]::GetFolderPath('Startup')) 'Condor Local.lnk'
$CondorBackupDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Condor\desktop-integration'
$CondorBackupShortcut = Join-Path $CondorBackupDirectory 'Condor Local.lnk'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $CondorTask -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $CondorProtocol) { Remove-Item -LiteralPath $CondorProtocol -Recurse }
    if ((Test-Path -LiteralPath $CondorBackupShortcut) -and -not (Test-Path -LiteralPath $CondorLegacyStartup)) {
        Move-Item -LiteralPath $CondorBackupShortcut -Destination $CondorLegacyStartup
    }
    Write-Output 'Inicializacao automatica e protocolo removidos. O cofre foi preservado.'
    return
}
foreach ($CondorRequired in @($CondorLauncher, $CondorRunner, (Join-Path $CondorRoot '.venv\Scripts\python.exe'))) {
    if (-not (Test-Path -LiteralPath $CondorRequired)) { throw "Componente ausente: $CondorRequired" }
}
# No URL is forwarded to the application: the protocol can only open Condor.
New-Item -Path "$CondorProtocol\shell\open\command" -Force | Out-Null
Set-Item -LiteralPath $CondorProtocol -Value 'URL:Condor Local Assistant'
New-ItemProperty -LiteralPath $CondorProtocol -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
Set-Item -LiteralPath "$CondorProtocol\shell\open\command" -Value ('"' + $CondorLauncher + '"')
$CondorUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$CondorArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $CondorRunner + '"'
$CondorAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $CondorArguments -WorkingDirectory $CondorRoot
$CondorTrigger = New-ScheduledTaskTrigger -AtLogOn -User $CondorUser
$CondorPrincipal = New-ScheduledTaskPrincipal -UserId $CondorUser -LogonType Interactive -RunLevel Limited
$CondorSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $CondorTask -Action $CondorAction -Trigger $CondorTrigger -Principal $CondorPrincipal -Settings $CondorSettings -Description 'Condor local, sem privilegios elevados. O cofre exige desbloqueio pelo dono.' -Force | Out-Null
if (Test-Path -LiteralPath $CondorLegacyStartup) {
    New-Item -ItemType Directory -Path $CondorBackupDirectory -Force | Out-Null
    if (-not (Test-Path -LiteralPath $CondorBackupShortcut)) {
        Move-Item -LiteralPath $CondorLegacyStartup -Destination $CondorBackupShortcut
    }
}
Write-Output 'Condor configurado para iniciar no login do Windows. Protocolo condor://open instalado.'
