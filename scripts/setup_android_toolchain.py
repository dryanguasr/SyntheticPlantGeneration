"""Download the pinned Windows Android toolchain into ignored outputs/mobile.

Requires network access. Does not change PATH, the registry or the training venv.
The SDK manager presents/accepts the SDK licences only with --accept-sdk-licenses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "outputs/mobile/toolchain"
GRADLE = "8.11.1"
JDK = "17.0.14_7"
CLI_VERSION = "19.0"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "UchuvaAndroidBuild/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2)


def download(url: str, name: str, checksum: str, algorithm: str = "sha256") -> Path:
    target = DEST / "downloads" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or hashlib.new(algorithm, target.read_bytes()).hexdigest() != checksum:
        print(f"Downloading {name}", flush=True)
        partial = target.with_suffix(target.suffix + ".part")
        for attempt in range(20):
            offset = partial.stat().st_size if partial.exists() else 0
            request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-", "User-Agent": "UchuvaAndroidBuild/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    with partial.open("ab" if response.status == 206 else "wb") as stream:
                        while chunk := response.read(65536):
                            stream.write(chunk)
                if hashlib.new(algorithm, partial.read_bytes()).hexdigest() == checksum:
                    break
            except OSError as error:
                print(f"Retry {name}: {type(error).__name__}", flush=True)
            time.sleep(2)
        if hashlib.new(algorithm, partial.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Checksum mismatch: {name}")
        partial.replace(target)
    return target


def extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if not (destination / member.filename).resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive member")
        source.extractall(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-sdk-licenses", action="store_true")
    parser.add_argument("--with-emulator", action="store_true", help="Also install emulator and an Android 10 x86_64 system image for integration tests")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("This bootstrap is for Windows; use Android Studio on other systems.")
    DEST.mkdir(parents=True, exist_ok=True)
    # Checksum published in github.com/corretto/corretto-17/releases/tag/17.0.14.7.1
    jdk_archive = download(
        "https://corretto.aws/downloads/resources/17.0.14.7.1/amazon-corretto-17.0.14.7.1-windows-x64-jdk.zip",
        "corretto-17.0.14.7.1.zip",
        "3f3cb5c5f75978dbc60f806b74331ba4bf5a5afe155b64a83844139684f50531",
    )
    java_home = DEST / f"jdk{JDK}"
    if not (java_home / "bin/java.exe").exists():
        extract(jdk_archive, DEST)
    gradle_url = f"https://downloads.gradle.org/distributions/gradle-{GRADLE}-bin.zip"
    gradle_archive = download(gradle_url, f"gradle-{GRADLE}-bin.zip", fetch(gradle_url + ".sha256").decode().strip())
    if not (DEST / f"gradle-{GRADLE}/bin/gradle.bat").exists():
        extract(gradle_archive, DEST)
    sdk_root = DEST / "android-sdk"
    manager = sdk_root / f"cmdline-tools/{CLI_VERSION}/bin/sdkmanager.bat"
    if not manager.exists():
        repository = ET.fromstring(fetch("https://dl.google.com/android/repository/repository2-1.xml"))
        item = next(p for p in repository.findall("remotePackage") if p.attrib["path"] == f"cmdline-tools;{CLI_VERSION}")
        archive = next(a for a in item.findall("archives/archive") if a.findtext("host-os") == "windows")
        complete = archive.find("complete")
        cli_zip = download("https://dl.google.com/android/repository/" + complete.findtext("url"), "android-cli.zip", complete.findtext("checksum"), "sha1")
        staging = DEST / "cli-extract"
        extract(cli_zip, staging)
        manager.parent.parent.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging / "cmdline-tools", manager.parent.parent, dirs_exist_ok=True)
    env = os.environ.copy()
    env.update(JAVA_HOME=str(java_home), ANDROID_HOME=str(sdk_root), ANDROID_USER_HOME=str(DEST / "android-user"), GRADLE_USER_HOME=str(DEST / "gradle-cache"))
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    if args.accept_sdk_licenses:
        subprocess.run([str(manager), f"--sdk_root={sdk_root}", "--licenses"], input="y\n" * 100, text=True, env=env, check=True)
    subprocess.run([str(manager), f"--sdk_root={sdk_root}", "platform-tools", "platforms;android-35", "build-tools;35.0.0"], env=env, check=True)
    if args.with_emulator:
        subprocess.run([str(manager), f"--sdk_root={sdk_root}", "emulator", "system-images;android-29;default;x86_64"], env=env, check=True)
    config = {key: env[key] for key in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_USER_HOME", "GRADLE_USER_HOME")}
    config["gradle"] = str(DEST / f"gradle-{GRADLE}/bin/gradle.bat")
    (DEST / "environment.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
