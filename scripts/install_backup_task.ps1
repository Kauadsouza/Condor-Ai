# Agenda o backup do Condor para rodar sozinho, todo dia.
#
# O backup manual so protege enquanto alguem lembra de rodar — e ninguem
# lembra. Esta tarefa roda no horario combinado, e tambem alguns minutos depois
# de voce ligar o PC, para o caso de ele estar desligado na hora marcada.
#
# A frase secreta e digitada UMA vez e guardada protegida pelo Windows (DPAPI):
# so este usuario, nesta maquina, consegue ler. O arquivo de backup em si
# continua portatil — ele abre com a frase, em qualquer computador. Ou seja: se
# este PC morrer, o backup guardado fora continua restauravel.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
#
# Para remover depois:
#   Unregister-ScheduledTask -TaskName "Condor - backup diario" -Confirm:$false

param(
    [string]$Destination,
    [string]$Hora = "20:00",
    [int]$Keep = 14
)

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$Backup = Join-Path $Raiz "scripts\backup_condor_data.ps1"
if (-not (Test-Path -LiteralPath $Backup)) { throw "Nao encontrei backup_condor_data.ps1 ao lado deste script." }

if (-not $Destination) {
    Write-Host "Onde guardar os backups? Prefira um pendrive ou uma pasta que sincroniza com a nuvem."
    Write-Host "Guardar so neste PC nao protege contra o PC morrer."
    $Destination = Read-Host "Pasta de destino"
}
if ([string]::IsNullOrWhiteSpace($Destination)) { throw "Destino vazio. Nada foi agendado." }
if (-not (Test-Path -LiteralPath $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }

# A frase vive fora do repositorio, na pasta de dados do usuario.
$PastaSegredo = Join-Path $env:LOCALAPPDATA "ARTX"
if (-not (Test-Path -LiteralPath $PastaSegredo)) { New-Item -ItemType Directory -Path $PastaSegredo -Force | Out-Null }
$ArquivoFrase = Join-Path $PastaSegredo "condor-backup.key"

if (Test-Path -LiteralPath $ArquivoFrase) {
    Write-Host "Ja existe uma frase guardada. Enter mantem a atual; digitar troca."
}
$Frase = Read-Host -AsSecureString "Frase secreta do backup (12+ caracteres)"
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Frase)
try { $Texto = [Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }

if ([string]::IsNullOrEmpty($Texto)) {
    if (-not (Test-Path -LiteralPath $ArquivoFrase)) { throw "Nenhuma frase guardada ainda: e preciso digitar uma." }
    Write-Host "Mantendo a frase que ja estava guardada."
} else {
    if ($Texto.Length -lt 12) { throw "Use ao menos 12 caracteres — o cofre do Condor exige isso." }
    ConvertFrom-SecureString -SecureString $Frase | Set-Content -LiteralPath $ArquivoFrase -Encoding ascii
    Write-Host "Frase guardada, protegida pela sua conta do Windows."
}

$Acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Backup`" " +
    "-Destination `"$Destination`" -PassphraseFile `"$ArquivoFrase`" -Keep $Keep"
)
$Gatilhos = @(
    (New-ScheduledTaskTrigger -Daily -At $Hora),
    (New-ScheduledTaskTrigger -AtLogOn)
)
$Gatilhos[1].Delay = "PT5M"
$Config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Condor - backup diario" -Action $Acao -Trigger $Gatilhos -Settings $Config -Description "Backup criptografado de ~/.condor" -Force | Out-Null

Write-Host ""
Write-Host "Agendado: todo dia as $Hora, e 5 minutos depois de cada login."
Write-Host "Destino: $Destination"
Write-Host "Mantendo os $Keep backups mais recentes."
Write-Host ""
Write-Host "Rodando uma vez agora para conferir que funciona..."
Start-ScheduledTask -TaskName "Condor - backup diario"
Start-Sleep -Seconds 20
$Gerados = Get-ChildItem -LiteralPath $Destination -Filter "condor-backup-*.enc" -File -ErrorAction SilentlyContinue
if ($Gerados) {
    $Ultimo = $Gerados | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "Funcionou: $($Ultimo.Name) ($([math]::Round($Ultimo.Length / 1MB, 2)) MB)"
    Write-Host ""
    Write-Host "Agora confirme que da para restaurar — um backup nunca testado e so uma esperanca:"
    Write-Host "  powershell -File scripts\restore_condor_data.ps1 -BackupFile `"$($Ultimo.FullName)`" -CondorHome `"$env:TEMP\condor-teste-restauracao`""
} else {
    Write-Host "A tarefa foi criada, mas ainda nao apareceu arquivo. Veja o historico no Agendador de Tarefas."
}
