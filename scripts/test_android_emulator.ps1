param([switch]$StartOnly)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$toolchain = Get-Content (Join-Path $repoRoot 'outputs/mobile/toolchain/environment.json') -Raw | ConvertFrom-Json
$env:JAVA_HOME = $toolchain.JAVA_HOME
$env:ANDROID_HOME = $toolchain.ANDROID_HOME
$env:ANDROID_USER_HOME = $toolchain.ANDROID_USER_HOME
$env:GRADLE_USER_HOME = $toolchain.GRADLE_USER_HOME
$env:ANDROID_AVD_HOME = Join-Path $repoRoot 'outputs/mobile/toolchain/avd'
$env:ANDROID_SERIAL = 'emulator-5580'
$adb = Join-Path $env:ANDROID_HOME 'platform-tools/adb.exe'
$manager = Join-Path $env:ANDROID_HOME 'cmdline-tools/19.0/bin/avdmanager.bat'
$emulator = Join-Path $env:ANDROID_HOME 'emulator/emulator.exe'
if (-not (Test-Path -LiteralPath $emulator)) { throw 'Ejecute setup_android_toolchain.py --with-emulator primero.' }
New-Item -ItemType Directory -Path $env:ANDROID_AVD_HOME -Force | Out-Null
$avdPath = Join-Path $env:ANDROID_AVD_HOME 'uchuva_api29.avd'
if (-not (Test-Path -LiteralPath (Join-Path $avdPath 'config.ini'))) {
    'no' | & $manager create avd --name uchuva_api29 --package 'system-images;android-29;default;x86_64' --device pixel_3a --path $avdPath
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el emulador.' }
}
$existing = & $adb devices
$startedHere = -not ($existing -match 'emulator-5580\s')
if ($startedHere) {
    $logRoot = Join-Path $repoRoot 'outputs/mobile/emulator'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    Start-Process -FilePath $emulator -WindowStyle Hidden -ArgumentList @('-avd','uchuva_api29','-port','5580','-no-window','-no-audio','-no-snapshot','-gpu','swiftshader_indirect','-camera-back','virtualscene','-camera-front','none','-memory','2048','-cores','2') -RedirectStandardOutput (Join-Path $logRoot 'stdout.log') -RedirectStandardError (Join-Path $logRoot 'stderr.log') | Out-Null
}
try {
    $deadline = (Get-Date).AddMinutes(4)
    do {
        Start-Sleep -Seconds 2
        $booted = & $adb -s emulator-5580 shell getprop sys.boot_completed 2>$null
    } while ($booted -ne '1' -and (Get-Date) -lt $deadline)
    if ($booted -ne '1') { throw 'El emulador no terminó de iniciar; revise outputs/mobile/emulator.' }
    & $adb -s emulator-5580 shell input keyevent 82
    if ($StartOnly) { Write-Output 'Emulador listo: emulator-5580'; return }
    & $toolchain.gradle -p (Join-Path $repoRoot 'mobile/android') --no-daemon --console=plain connectedDebugAndroidTest
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas instrumentadas.' }
} finally {
    if ($startedHere -and -not $StartOnly) { & $adb -s emulator-5580 emu kill }
}
