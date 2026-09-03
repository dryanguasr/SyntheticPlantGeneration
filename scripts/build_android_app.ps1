param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $repoRoot 'outputs/mobile/toolchain/environment.json'
if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw 'Ejecute primero scripts/setup_android_toolchain.py --accept-sdk-licenses.'
}
$toolchain = Get-Content -LiteralPath $environmentFile -Raw | ConvertFrom-Json
$env:JAVA_HOME = $toolchain.JAVA_HOME
$env:ANDROID_HOME = $toolchain.ANDROID_HOME
$env:ANDROID_USER_HOME = $toolchain.ANDROID_USER_HOME
$env:GRADLE_USER_HOME = $toolchain.GRADLE_USER_HOME
$gradleTasks = @('assembleDebug', 'assembleDebugAndroidTest', 'lintDebug')
if (-not $SkipTests) { $gradleTasks += 'testDebugUnitTest' }
Push-Location (Join-Path $repoRoot 'mobile/android')
try {
    & $toolchain.gradle --no-daemon --console=plain @gradleTasks
    if ($LASTEXITCODE -ne 0) { throw "Gradle terminó con código $LASTEXITCODE" }
    $releaseDirectory = Join-Path $repoRoot 'outputs/mobile/apk'
    New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
    Copy-Item -LiteralPath 'app/build/outputs/apk/debug/app-debug.apk' -Destination (Join-Path $releaseDirectory 'uchuva-aruco-debug.apk') -Force
    Get-FileHash -LiteralPath (Join-Path $releaseDirectory 'uchuva-aruco-debug.apk') -Algorithm SHA256
} finally { Pop-Location }
