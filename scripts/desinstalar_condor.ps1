# Remove o aplicativo Condor desta pasta. A memória, o cofre, a identidade e
# os modelos em ~/.condor são PRESERVADOS: reinstalar traz tudo de volta.
$ErrorActionPreference = "Continue"
$Raiz = Split-Path -Parent $PSScriptRoot

Add-Type -AssemblyName System.Windows.Forms
# Só apaga uma pasta criada pelo CondorSetup.exe; nunca um repositório de código.
$Perfil = [Environment]::GetFolderPath("UserProfile").TrimEnd("\") + "\"
$Estado = (Join-Path $Perfil ".condor") + "\"
$RaizCompleta = [IO.Path]::GetFullPath($Raiz).TrimEnd("\") + "\"
$Perigosa = $RaizCompleta.Length -le 4 -or $Perfil.StartsWith($RaizCompleta, [StringComparison]::OrdinalIgnoreCase) -or
    $Estado.StartsWith($RaizCompleta, [StringComparison]::OrdinalIgnoreCase) -or
    $RaizCompleta.StartsWith($Estado, [StringComparison]::OrdinalIgnoreCase)
if ($Perigosa -or -not (Test-Path -LiteralPath (Join-Path $Raiz ".condor-instalado"))) {
    [System.Windows.Forms.MessageBox]::Show(
        "Esta pasta nao foi instalada pelo CondorSetup ($Raiz). Nada foi removido.",
        "Desinstalar CONDOR", "OK", "Warning") | Out-Null
    exit 2
}
$Resposta = [System.Windows.Forms.MessageBox]::Show(
    "Remover o aplicativo CONDOR deste PC?`n`nSua memoria, cofre e modelos em ~/.condor serao mantidos.",
    "Desinstalar CONDOR", "YesNo", "Question")
if ($Resposta -ne "Yes") { exit 1 }

# Para o núcleo, a janela e o Ollama que rodam a partir desta pasta.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Raiz) -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

& (Join-Path $PSScriptRoot "install_desktop_integration.ps1") -Remove | Out-Null
foreach ($Pasta in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Startup"))) {
    foreach ($Nome in @("Condor.lnk", "Condor Local.lnk")) {
        $Atalho = Join-Path $Pasta $Nome
        if (Test-Path -LiteralPath $Atalho) {
            $Alvo = (New-Object -ComObject WScript.Shell).CreateShortcut($Atalho).TargetPath
            if ($Alvo -and $Alvo.StartsWith($Raiz, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $Atalho -Force }
        }
    }
}
Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CondorAI" -Recurse -Force -ErrorAction SilentlyContinue

# A pasta não pode ser apagada enquanto este script roda de dentro dela.
Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -ArgumentList "/c timeout /t 3 /nobreak >nul & rmdir /s /q `"$Raiz`""
[System.Windows.Forms.MessageBox]::Show("CONDOR removido. Sua memoria continua em ~/.condor.", "CONDOR") | Out-Null
