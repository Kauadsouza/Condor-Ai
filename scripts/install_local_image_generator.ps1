[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$profileRoot = [Environment]::GetFolderPath('UserProfile')
$condorState = Join-Path $profileRoot '.condor'
$toolBase = Join-Path $condorState 'tools\stable-diffusion.cpp'
$toolRoot = Join-Path $toolBase 'master-827-97d2990'
$archive = Join-Path $toolBase 'sd-master-97d2990-bin-win-vulkan-x64.zip'
$modelRoot = Join-Path $condorState 'models\image'
$model = Join-Path $modelRoot 'sdxl_lightning_4step.safetensors'
$quantizedModel = Join-Path $modelRoot 'sdxl_lightning_4step.q4_0.gguf'

$binaryUrl = 'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-827-97d2990/sd-master-97d2990-bin-win-vulkan-x64.zip'
$binarySha256 = '06c0ca546c63419b32cd4982e1b12d7c6965f3408373fd3561b0c85635931285'
$modelUrl = 'https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_4step.safetensors'
$modelSha256 = 'e0d996ee0013e79d9d3561f50fcafb9a17e3ff07b780358e3b66d67932c4d490'

New-Item -ItemType Directory -Force -Path $toolBase, $modelRoot | Out-Null

if (-not (Test-Path -LiteralPath $archive)) {
    Write-Host '[1/5] Baixando stable-diffusion.cpp oficial...'
    Invoke-WebRequest -Uri $binaryUrl -OutFile $archive
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant() -ne $binarySha256) {
    throw 'A assinatura SHA-256 do executavel local nao confere.'
}

if (-not (Test-Path -LiteralPath (Join-Path $toolRoot 'sd-cli.exe'))) {
    Write-Host '[2/5] Instalando o motor local...'
    New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $toolRoot
}

if (-not (Test-Path -LiteralPath $model)) {
    Write-Host '[3/5] Baixando SDXL-Lightning 4-step oficial (cerca de 6,5 GiB)...'
    & curl.exe -L --fail --retry 3 --continue-at - --output $model $modelUrl
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar o modelo local.' }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $model).Hash.ToLowerInvariant() -ne $modelSha256) {
    throw 'A assinatura SHA-256 do modelo local nao confere.'
}

$sdCli = Join-Path $toolRoot 'sd-cli.exe'
if (-not (Test-Path -LiteralPath $quantizedModel)) {
    Write-Host '[4/5] Convertendo para GGUF Q4 (adequado a GPU de 4 GB)...'
    & $sdCli -M convert -m $model -o $quantizedModel -v --type q4_0
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $quantizedModel)) {
        throw 'Falha ao converter o modelo local para GGUF Q8.'
    }
}

Write-Host '[5/5] Validando os dispositivos de inferencia...'
& $sdCli --list-devices
if ($LASTEXITCODE -ne 0) { throw 'O motor local foi instalado, mas nao iniciou corretamente.' }
Write-Host 'Gerador de imagens local pronto. Reinicie o Condor.'
