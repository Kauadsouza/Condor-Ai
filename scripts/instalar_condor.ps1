# Instala (ou repara) o Condor na pasta onde este script está.
# Executado pelo CondorSetup.exe; também funciona à mão:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_condor.ps1 [-ComImagem] [-SegundoPlano]
# As linhas "##CONDOR-PASSO n/N" alimentam a barra de progresso do instalador.
# Memória, cofre e modelos ficam em ~/.condor e nunca são apagados ou recriados.
param(
    [switch]$ComImagem,
    [switch]$SegundoPlano
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # a barra do Invoke-WebRequest deixa o download 10x mais lento
$Raiz = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Raiz ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$StateRoot = if ($env:CONDOR_HOME) { [IO.Path]::GetFullPath($env:CONDOR_HOME) } else { Join-Path ([Environment]::GetFolderPath("UserProfile")) ".condor" }
$OllamaExe = Join-Path $Raiz "runtime\ollama\windows\ollama.exe"
$Total = 9

function Passo([int]$N, [string]$Texto) {
    Write-Output "##CONDOR-PASSO $N/$Total $Texto"
}

function Test-Porta([int]$Porta) {
    $Cliente = [Net.Sockets.TcpClient]::new()
    try {
        $Resultado = $Cliente.BeginConnect("127.0.0.1", $Porta, $null, $null)
        return $Resultado.AsyncWaitHandle.WaitOne(400) -and $Cliente.Connected
    } catch { return $false } finally { $Cliente.Dispose() }
}

function Find-Python {
    # Qualquer Python 3.11+ já instalado serve; o Condor usa um ambiente próprio.
    $Candidatos = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $ErrorActionPreference = "Continue"
        $Lista = @(& py -0p 2>$null)
        $ErrorActionPreference = "Stop"
        foreach ($Linha in $Lista) {
            if ($Linha -match '-V:\S+\s+\*?\s*(.+?python\.exe)\s*$') { $Candidatos += $Matches[1].Trim() }
        }
    }
    $Privado = Join-Path $Raiz "python\python.exe"
    $Candidatos += @($Privado, (Get-Command python -ErrorAction SilentlyContinue).Source) | Where-Object { $_ }
    foreach ($Candidato in $Candidatos) {
        # O "python.exe" da Microsoft Store (WindowsApps) é só um atalho que
        # abre a loja e escreve erro: não serve.
        if (-not (Test-Path -LiteralPath $Candidato) -or $Candidato -like '*\WindowsApps\*') { continue }
        try {
            $ErrorActionPreference = "Continue"
            $Versao = (& $Candidato -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $Versao -match '^\d+\.\d+$' -and [version]$Versao -ge [version]"3.11") { return $Candidato }
        } catch {
            continue
        } finally {
            $ErrorActionPreference = "Stop"
        }
    }
    return $null
}

function Install-PythonPrivado {
    # Python oficial, só para este usuário, dentro da pasta do Condor.
    $Versao = "3.12.10"
    $Instalador = Join-Path ([IO.Path]::GetTempPath()) "condor-python-$Versao.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$Versao/python-$Versao-amd64.exe" -OutFile $Instalador
    $Assinatura = Get-AuthenticodeSignature -LiteralPath $Instalador
    if ($Assinatura.Status -ne "Valid" -or $Assinatura.SignerCertificate.Subject -notmatch "Python Software Foundation") {
        Remove-Item -LiteralPath $Instalador -Force
        throw "O instalador do Python baixado nao tem a assinatura da Python Software Foundation."
    }
    $Destino = Join-Path $Raiz "python"
    $Processo = Start-Process -FilePath $Instalador -Wait -PassThru -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0",
        "Include_doc=0", "Shortcuts=0", "AssociateFiles=0", "TargetDir=`"$Destino`""
    )
    Remove-Item -LiteralPath $Instalador -Force -ErrorAction SilentlyContinue
    if ($Processo.ExitCode -ne 0) { throw "O Python nao instalou (codigo $($Processo.ExitCode))." }
    return (Join-Path $Destino "python.exe")
}

Passo 1 "Procurando o Python"
$Python = Find-Python
if (-not $Python) {
    Write-Output "Python 3.11+ nao encontrado; instalando uma copia privada do Python 3.12..."
    $Python = Install-PythonPrivado
}
Write-Output "Usando $Python"

Passo 2 "Criando o ambiente do Condor e instalando as bibliotecas (alguns minutos)"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Nao consegui criar o ambiente Python." }
}
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -e $Raiz
if ($LASTEXITCODE -ne 0) { throw "A instalacao das bibliotecas falhou (veja o log acima)." }

Passo 3 "Baixando a voz local (Whisper, Piper e a palavra Condor)"
& $VenvPython (Join-Path $PSScriptRoot "install_voice_models.py")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar os modelos de voz." }

Passo 4 "Instalando o motor de IA local (Ollama)"
& (Join-Path $PSScriptRoot "install_local_ai.ps1")

Passo 5 "Baixando o cerebro, a visao e a memoria (reaproveita o que ja existe)"
$OllamaIniciado = $null
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_MODELS = Join-Path $StateRoot "models"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NOHISTORY = "1"
try {
    if (-not (Test-Porta 11434)) {
        $OllamaIniciado = Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WorkingDirectory $Raiz -WindowStyle Hidden -PassThru
        for ($i = 0; $i -lt 80 -and -not (Test-Porta 11434); $i++) { Start-Sleep -Milliseconds 250 }
        if (-not (Test-Porta 11434)) { throw "A IA local nao iniciou em 127.0.0.1:11434." }
    }
    foreach ($Modelo in @("qwen3:4b-instruct", "qwen3-vl:2b", "embeddinggemma")) {
        Write-Output "Modelo $Modelo"
        & $OllamaExe pull $Modelo
        if ($LASTEXITCODE -ne 0) { throw "Falha ao baixar o modelo $Modelo." }
    }

    Passo 6 "Criacao de imagem local"
    if ($ComImagem) {
        & (Join-Path $PSScriptRoot "install_local_image_generator.ps1")
    } else {
        Write-Output "Pulado (pode instalar depois rodando o CondorSetup de novo)."
    }

    Passo 7 "Ferramentas de programacao (Arduino)"
    try { & (Join-Path $PSScriptRoot "install_arduino_cli.ps1") } catch { Write-Output "Arduino CLI pendente: $($_.Exception.Message)" }

    Passo 8 "Criando o aplicativo, atalhos e desinstalador"
    & (Join-Path $PSScriptRoot "install_app_shortcut.ps1")
    if ($SegundoPlano) {
        # Só o núcleo invisível no login, esperando "Condor". Nenhuma janela abre sozinha.
        & (Join-Path $PSScriptRoot "install_desktop_integration.ps1")
    } else {
        & (Join-Path $PSScriptRoot "install_desktop_integration.ps1") -Remove
    }
    $Chave = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CondorAI"
    New-Item -Path $Chave -Force | Out-Null
    $Versao = (& $VenvPython -c "import importlib.metadata as m; print(m.version('condor-local'))" 2>$null)
    $Valores = @{
        DisplayName = "CONDOR"; Publisher = "Kaua Diniz Souza"; DisplayVersion = "$Versao"
        InstallLocation = $Raiz; DisplayIcon = (Join-Path $Raiz "condor\ui\assets\condor-logo.ico")
        UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $PSScriptRoot 'desinstalar_condor.ps1')`""
    }
    foreach ($Item in $Valores.GetEnumerator()) { New-ItemProperty -Path $Chave -Name $Item.Key -Value $Item.Value -PropertyType String -Force | Out-Null }
    New-ItemProperty -Path $Chave -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $Chave -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null

    Passo 9 "Diagnostico final"
    $Argumentos = @((Join-Path $PSScriptRoot "doctor.py"))
    if (-not $ComImagem) { $Argumentos += "--sem-imagem" }
    & $VenvPython @Argumentos
    if ($LASTEXITCODE -ne 0) { Write-Output "Atencao: o diagnostico marcou itens PENDENTES acima; o Condor abre mesmo assim." }
} finally {
    if ($OllamaIniciado -and -not $OllamaIniciado.HasExited) {
        Stop-Process -Id $OllamaIniciado.Id
        $Runtime = Join-Path $Raiz "runtime\ollama"
        Get-Process llama-server -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and $_.Path.StartsWith($Runtime, [StringComparison]::OrdinalIgnoreCase) } |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
Write-Output "##CONDOR-PRONTO"
