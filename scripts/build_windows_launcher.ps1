$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $ProjectRoot "windows\CondorLauncher.cs"
$Icon = Join-Path $ProjectRoot "condor\ui\assets\condor-logo.ico"
$Output = Join-Path $ProjectRoot "Condor.exe"
$Compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"

foreach ($Required in @($Source, $Icon, $Compiler)) {
    if (-not (Test-Path -LiteralPath $Required)) {
        throw "Componente necessario para a identidade do Condor nao encontrado: $Required"
    }
}

& $Compiler /nologo /target:winexe /optimize+ /platform:anycpu `
    /reference:System.Windows.Forms.dll /win32icon:"$Icon" /out:"$Output" "$Source"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Output)) {
    throw "Nao foi possivel construir o inicializador nativo do Condor."
}

Write-Host "Inicializador nativo criado em $Output" -ForegroundColor Green
