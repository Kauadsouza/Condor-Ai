# Restaura um backup criptografado gerado por scripts\backup_condor_data.ps1
# em um Windows novo (ou no mesmo PC apos perda de dados).
#
# Uso:
#   powershell -File scripts\restore_condor_data.ps1 -BackupFile "E:\Backups\Condor\condor-backup-20260914-101112.enc"
#
# Pastas ja existentes em ~/.condor sao renomeadas com sufixo ".before-restore-<data>"
# em vez de sobrescritas.

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$CondorHome = $(if ($env:CONDOR_HOME) { $env:CONDOR_HOME } else { Join-Path $HOME ".condor" })
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BackupFile)) {
    throw "Arquivo de backup nao encontrado: $BackupFile"
}

Write-Host "Digite a frase secreta usada para criptografar este backup:"
$SecurePassword = Read-Host -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
try {
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
}

$AllBytes = [System.IO.File]::ReadAllBytes($BackupFile)
if ($AllBytes.Length -le 16) {
    throw "Arquivo de backup invalido ou corrompido."
}
$Salt = $AllBytes[0..15]
$CipherBytes = $AllBytes[16..($AllBytes.Length - 1)]

$DeriveBytes = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Password, $Salt, 200000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$Key = $DeriveBytes.GetBytes(32)
$Iv = $DeriveBytes.GetBytes(16)

$Aes = [System.Security.Cryptography.Aes]::Create()
$Aes.Key = $Key
$Aes.IV = $Iv
$Aes.Mode = [System.Security.Cryptography.CipherMode]::CBC

$Decryptor = $Aes.CreateDecryptor()
try {
    $DecryptedBytes = $Decryptor.TransformFinalBlock($CipherBytes, 0, $CipherBytes.Length)
} catch {
    throw "Falha ao descriptografar. Frase secreta incorreta ou arquivo corrompido."
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempZip = Join-Path $env:TEMP "condor-restore-$Timestamp.zip"
$ExtractDir = Join-Path $env:TEMP "condor-restore-extract-$Timestamp"

try {
    [System.IO.File]::WriteAllBytes($TempZip, $DecryptedBytes)
    Expand-Archive -LiteralPath $TempZip -DestinationPath $ExtractDir

    if (-not (Test-Path -LiteralPath $CondorHome)) {
        New-Item -ItemType Directory -Path $CondorHome | Out-Null
    }

    Get-ChildItem -LiteralPath $ExtractDir | ForEach-Object {
        $Target = Join-Path $CondorHome $_.Name
        if (Test-Path -LiteralPath $Target) {
            $PreservedName = "$($_.Name).before-restore-$Timestamp"
            Rename-Item -LiteralPath $Target -NewName $PreservedName
        }
        Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse
    }

    Write-Host ""
    Write-Host "Restauracao concluida em: $CondorHome"
    Write-Host "Dados anteriores (se existiam) foram preservados com sufixo '.before-restore-$Timestamp'."
    Write-Host "Reinicie o Condor para carregar a memoria e identidade restauradas."
}
finally {
    Remove-Item -LiteralPath $TempZip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
}
