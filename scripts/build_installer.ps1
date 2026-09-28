# Gera dist\CondorSetup.exe: um único instalador com o código do Condor embutido.
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
# Entra o que o Git conhece (versionado + novo não ignorado). Nunca entram
# .venv, runtime, modelos, ~/.condor, segredos ou saídas geradas.
$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Raiz "dist"
$Pacote = Join-Path $Dist "condor-payload.zip"
$Saida = Join-Path $Dist "CondorSetup.exe"
$Fonte = Join-Path $Raiz "windows\CondorSetup.cs"
$Icone = Join-Path $Raiz "condor\ui\assets\condor-logo.ico"
$Compilador = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$FrameworkDir = Split-Path -Parent $Compilador

# Pastas que nunca vão para o instalador, mesmo se aparecerem no Git.
$Fora = @(".github/", "cloud/", "testes/fixtures/", "treino/dados/")

Push-Location $Raiz
try {
    $Arquivos = @(git ls-files --cached --others --exclude-standard) | Where-Object {
        $Arquivo = $_
        (Test-Path -LiteralPath $Arquivo -PathType Leaf) -and -not ($Fora | Where-Object { $Arquivo.StartsWith($_) })
    }
} finally {
    Pop-Location
}
if ($Arquivos.Count -lt 50) { throw "Poucos arquivos encontrados ($($Arquivos.Count)); rode dentro do repositorio do Condor." }
foreach ($Proibido in @(".env", "config.yaml", "vault.json")) {
    if ($Arquivos | Where-Object { (Split-Path -Leaf $_) -eq $Proibido }) { throw "Arquivo sensivel no pacote: $Proibido" }
}

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Remove-Item -LiteralPath $Pacote, $Saida -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::Open($Pacote, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($Arquivo in $Arquivos) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $Zip, (Join-Path $Raiz $Arquivo), $Arquivo.Replace("\", "/"),
            [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally {
    $Zip.Dispose()
}
Write-Host ("Pacote: {0} arquivos, {1:N1} MB" -f $Arquivos.Count, ((Get-Item $Pacote).Length / 1MB))

& $Compilador /nologo /target:winexe /optimize+ /platform:anycpu `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Management.dll `
    "/reference:$FrameworkDir\System.IO.Compression.dll" "/reference:$FrameworkDir\System.IO.Compression.FileSystem.dll" `
    "/resource:$Pacote,CondorPayload" /win32icon:"$Icone" /out:"$Saida" "$Fonte"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Saida)) { throw "Nao consegui compilar o CondorSetup.exe." }
Remove-Item -LiteralPath $Pacote
Write-Host ("Instalador pronto: {0} ({1:N1} MB)" -f $Saida, ((Get-Item $Saida).Length / 1MB)) -ForegroundColor Green
