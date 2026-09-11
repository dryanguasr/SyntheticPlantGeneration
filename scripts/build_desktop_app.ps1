param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo 'outputs/desktop/venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & (Join-Path $repo '.venv-training/Scripts/python.exe') -m venv (Join-Path $repo 'outputs/desktop/venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de PC' }
}
if (-not $SkipInstall) {
    & $venv -m pip install -r (Join-Path $repo 'desktop/requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de PC' }
}
& $venv -m PyInstaller --clean --noconfirm --windowed --onedir --name UchuvaArUcoPC `
    --paths (Join-Path $repo 'desktop') `
    --distpath (Join-Path $repo 'outputs/desktop/dist') `
    --workpath (Join-Path $repo 'outputs/desktop/build') `
    --specpath (Join-Path $repo 'outputs/desktop') `
    --add-data "$(Join-Path $repo 'mobile/android/app/src/main/assets/detector.onnx');assets" `
    --add-data "$(Join-Path $repo 'mobile/android/app/src/main/assets/model_manifest.json');assets" `
    (Join-Path $repo 'desktop/run_app.py')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar la app PC' }
$dist = Join-Path $repo 'outputs/desktop/dist/UchuvaArUcoPC'
Copy-Item -LiteralPath (Join-Path $repo 'desktop/mediamtx.yml') -Destination $dist -Force
if (Test-Path -LiteralPath (Join-Path $repo 'outputs/desktop/server/mediamtx.exe')) {
    Copy-Item -LiteralPath (Join-Path $repo 'outputs/desktop/server/mediamtx.exe') -Destination $dist -Force
    Copy-Item -LiteralPath (Join-Path $repo 'outputs/desktop/server/LICENSE') -Destination (Join-Path $dist 'LICENSE-MediaMTX') -Force
    '@"%~dp0mediamtx.exe" "%~dp0mediamtx.yml"' | Set-Content -LiteralPath (Join-Path $dist 'Iniciar servidor RTMP.cmd')
}
Copy-Item -LiteralPath (Join-Path $repo 'docs/guides/video_dron_pc_rtmp.md') -Destination (Join-Path $dist 'LEEME.md') -Force
Get-FileHash -LiteralPath (Join-Path $dist 'UchuvaArUcoPC.exe') -Algorithm SHA256
$archive = Join-Path $repo 'outputs/desktop/UchuvaArUcoPC-0.3.0-windows-x64.zip'
Compress-Archive -LiteralPath $dist -DestinationPath $archive -Force
Get-FileHash -LiteralPath $archive -Algorithm SHA256
