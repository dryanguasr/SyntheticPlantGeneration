$ErrorActionPreference = 'Stop'
$folder = Join-Path (Split-Path -Parent $PSScriptRoot) 'outputs/desktop/server'
if (-not (Test-Path -LiteralPath (Join-Path $folder 'mediamtx.exe'))) { throw 'Ejecute scripts/setup_rtmp_server.ps1 primero.' }
# Foreground process: closing this terminal stops the explicitly started server.
& (Join-Path $folder 'mediamtx.exe') (Join-Path $folder 'mediamtx.yml')
