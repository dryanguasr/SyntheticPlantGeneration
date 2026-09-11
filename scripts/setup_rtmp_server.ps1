param([ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.21.0')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $repo 'outputs/desktop/server'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$archive = Join-Path $folder "mediamtx_v${Version}_windows_amd64.zip"
$url = "https://github.com/bluenviron/mediamtx/releases/download/v${Version}/mediamtx_v${Version}_windows_amd64.zip"
Invoke-WebRequest -Uri $url -OutFile $archive
if ($Version -eq '1.21.0' -and (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '8A58A9B8C25EE99A96C23DC0A17F39ACE3072C01D2E148329073C64DDF83493D') {
    throw 'El archivo MediaMTX difiere del paquete 1.21.0 validado en este proyecto.'
}
# Record the downloaded release digest for deployment provenance.
Get-FileHash -LiteralPath $archive -Algorithm SHA256 | ConvertTo-Json | Set-Content (Join-Path $folder 'download-sha256.json')
Expand-Archive -LiteralPath $archive -DestinationPath $folder -Force
Copy-Item -LiteralPath (Join-Path $repo 'desktop/mediamtx.yml') -Destination $folder -Force
Write-Output "Servidor preparado en $folder. Ejecute scripts/start_rtmp_server.ps1 cuando quiera recibir video."
