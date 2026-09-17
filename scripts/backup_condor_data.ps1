# Cria um backup criptografado (AES-256) da pasta privada do Condor (~/.condor).
# So inclui dados unicos e irrecuperaveis: config, memoria, seguranca, auditoria e logs.
# NAO inclui "models" nem "tools", que sao redownloadaveis e podem ocupar dezenas de GB.
#
# Uso:
#   powershell -File scripts\backup_condor_data.ps1 -Destination "E:\Backups\Condor"
#
# Guarde o arquivo .enc gerado fora deste PC (pendrive, nuvem pessoal) e a frase secreta
# em um cofre de senhas separado. Sem a frase, o backup nao pode ser restaurado.

param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [string]$CondorHome = $(if ($env:CONDOR_HOME) { $env:CONDOR_HOME } else { Join-Path $HOME ".condor" }),
    # Arquivo com a frase protegida pelo Windows (DPAPI), usado pela tarefa
    # agendada — que nao tem ninguem para digitar nada. Veja install_backup_task.ps1.
    [string]$PassphraseFile,
    # Quantos backups manter na pasta de destino. 0 mantem todos.
    [int]$Keep = 14
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $CondorHome)) {
    throw "Pasta do Condor nao encontrada em '$CondorHome'."
}

$FoldersToBackup = @("memory", "security", "audit", "logs", "backups")
$FilesToBackup = @("config.yaml")

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StagingDir = Join-Path $env:TEMP "condor-backup-$Timestamp"
$ZipPath = Join-Path $env:TEMP "condor-backup-$Timestamp.zip"

New-Item -ItemType Directory -Path $StagingDir | Out-Null

try {
    $Found = $false
    foreach ($Folder in $FoldersToBackup) {
        $Src = Join-Path $CondorHome $Folder
        if (Test-Path -LiteralPath $Src) {
            Copy-Item -LiteralPath $Src -Destination (Join-Path $StagingDir $Folder) -Recurse
            $Found = $true
        }
    }
    foreach ($File in $FilesToBackup) {
        $Src = Join-Path $CondorHome $File
        if (Test-Path -LiteralPath $Src) {
            Copy-Item -LiteralPath $Src -Destination (Join-Path $StagingDir $File)
            $Found = $true
        }
    }
    if (-not $Found) {
        throw "Nenhum dado encontrado em '$CondorHome'. Nada para copiar."
    }

    Compress-Archive -Path (Join-Path $StagingDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

    if (-not (Test-Path -LiteralPath $Destination)) {
        New-Item -ItemType Directory -Path $Destination | Out-Null
    }
    $EncryptedPath = Join-Path $Destination "condor-backup-$Timestamp.enc"

    if ($PassphraseFile) {
        # A frase fica protegida pelo DPAPI: so este usuario do Windows, nesta
        # maquina, consegue ler o arquivo. O backup gerado continua portatil —
        # ele e aberto com a frase, em qualquer computador.
        if (-not (Test-Path -LiteralPath $PassphraseFile)) {
            throw "Arquivo de frase nao encontrado em '$PassphraseFile'. Rode install_backup_task.ps1 de novo."
        }
        # Trim: o arquivo termina com quebra de linha e o ConvertTo-SecureString recusa.
        $FraseGuardada = (Get-Content -LiteralPath $PassphraseFile -Raw).Trim()
        if (-not $FraseGuardada) { throw "Arquivo de frase vazio em '$PassphraseFile'." }
        $SecurePassword = ConvertTo-SecureString $FraseGuardada
    } else {
        Write-Host "Digite uma frase secreta para criptografar este backup (guarde-a fora deste PC):"
        $SecurePassword = Read-Host -AsSecureString
    }
    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try {
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    if ([string]::IsNullOrEmpty($Password)) {
        throw "Frase secreta vazia. Backup cancelado."
    }

    $Salt = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Salt)

    $DeriveBytes = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Password, $Salt, 200000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    $Key = $DeriveBytes.GetBytes(32)
    $Iv = $DeriveBytes.GetBytes(16)

    $Aes = [System.Security.Cryptography.Aes]::Create()
    $Aes.Key = $Key
    $Aes.IV = $Iv
    $Aes.Mode = [System.Security.Cryptography.CipherMode]::CBC

    $InputBytes = [System.IO.File]::ReadAllBytes($ZipPath)
    $Encryptor = $Aes.CreateEncryptor()
    $EncryptedBytes = $Encryptor.TransformFinalBlock($InputBytes, 0, $InputBytes.Length)

    $OutStream = [System.IO.File]::Create($EncryptedPath)
    try {
        $OutStream.Write($Salt, 0, $Salt.Length)
        $OutStream.Write($EncryptedBytes, 0, $EncryptedBytes.Length)
    } finally {
        $OutStream.Close()
    }

    Write-Host ""
    Write-Host "Backup criptografado criado em: $EncryptedPath"
    Write-Host "Guarde a frase secreta em um cofre de senhas separado deste PC."
    Write-Host "Sem ela, o backup nao pode ser restaurado por ninguem, incluindo voce."

    # Sem limpeza, a pasta cresce para sempre e um dia enche o disco — que e
    # justamente quando o backup para de rodar, sem ninguem perceber.
    if ($Keep -gt 0) {
        $Antigos = Get-ChildItem -LiteralPath $Destination -Filter "condor-backup-*.enc" -File |
            Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep
        foreach ($Velho in $Antigos) {
            Remove-Item -LiteralPath $Velho.FullName -Force -ErrorAction SilentlyContinue
        }
        if ($Antigos) { Write-Host "Removidos $($Antigos.Count) backups antigos, mantendo os $Keep mais recentes." }
    }
}
finally {
    Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
}
