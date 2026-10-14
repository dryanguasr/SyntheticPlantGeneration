"""Run one local pilot stage with a shared deadline and sampled process-tree RSS.

On Linux, use this inside a transient systemd user service with MemorySwapMax=0
and MemoryMax for a kernel-enforced aggregate limit. RSS samples can count shared
pages twice and are not a substitute for that cgroup limit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True, help="UTC Unix seconds, shared by all retries")
    parser.add_argument("--seconds", type=float, default=900)
    parser.add_argument("--ram-gib", type=float, default=10)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.seconds <= 0 or args.ram_gib <= 0:
        parser.error("A command and positive limits are required")
    start = time.time()
    deadline = min(args.deadline, start + args.seconds)
    if deadline <= start:
        raise SystemExit("Shared pilot deadline has expired")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"script_version": "reconstruction-pilot/0.1", "seed": 20261001,
              "parameter_preset": "pilot_2h", "command": command, "start_epoch": start, "deadline_epoch": deadline,
              "ram_limit_bytes": int(args.ram_gib * 1024**3), "peak_tree_rss_bytes": 0,
              "rss_note": "1-second samples; shared pages may be counted more than once",
              "gpu_memory_note": "Device-wide memory sampled every 5 seconds; includes unrelated allocations",
              "peak_device_memory_mib": None,
              "status": "running"}
    (args.output / "stage.json").write_text(json.dumps(report, indent=2))
    process = None
    try:
        with (args.output / "command.log").open("w") as log, (args.output / "resources.jsonl").open("w") as resources:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != "nt")
            tracked = {}
            next_gpu_sample = start
            gpu_tool = shutil.which("nvidia-smi")
            while True:
                now = time.time()
                try:
                    parent = psutil.Process(process.pid)
                    for p in [parent, *parent.children(recursive=True)]:
                        tracked[(p.pid, p.create_time())] = p
                except psutil.NoSuchProcess:
                    pass
                rss = 0
                for key, p in list(tracked.items()):
                    try:
                        rss += p.memory_info().rss
                    except psutil.NoSuchProcess:
                        del tracked[key]
                report["peak_tree_rss_bytes"] = max(rss, report["peak_tree_rss_bytes"])
                sample = {"epoch": now, "rss_bytes": rss, "pids": [key[0] for key in tracked]}
                if gpu_tool and now >= next_gpu_sample:
                    try:
                        gpu = subprocess.run([gpu_tool, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=2)
                        memory = sum(float(line) for line in gpu.stdout.splitlines())
                        if gpu.returncode == 0 and gpu.stdout.strip():
                            sample["device_memory_mib"] = memory
                            report["peak_device_memory_mib"] = max(report["peak_device_memory_mib"] or 0, memory)
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        pass
                    next_gpu_sample = now + 5
                resources.write(json.dumps(sample) + "\n")
                resources.flush()
                if process.poll() is not None:
                    report.update(returncode=process.returncode, status="completed" if process.returncode == 0 else "failed")
                    break
                if now >= deadline or rss > report["ram_limit_bytes"]:
                    report["status"] = "deadline" if now >= deadline else "ram_limit"
                    break
                time.sleep(min(1, max(.01, deadline - now)))
    finally:
        if report["status"] == "running":
            report["status"] = "interrupted_or_error"
        if process is not None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    time.sleep(.5)
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                for p in reversed(list(tracked.values())):
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
            process.wait(timeout=5)
        report.update(end_epoch=time.time(), elapsed_seconds=time.time() - start)
        (args.output / "stage.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
