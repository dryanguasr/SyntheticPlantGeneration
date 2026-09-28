"""Run a bounded, single-Blender pilot with memory monitoring and preserved logs."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong)] + [
        (name,ctypes.c_ulonglong) for name in ("total_physical","available_physical","total_page",
                                              "available_page","total_virtual","available_virtual","extended")]


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb",ctypes.c_ulong),("page_faults",ctypes.c_ulong)] + [
        (name,ctypes.c_size_t) for name in ("peak_working_set","working_set","peak_paged","paged",
                                          "peak_nonpaged","nonpaged","pagefile","peak_pagefile")]


def memory(pid):
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("Cannot monitor available RAM")
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x0400 | 0x0010,False,pid)
    counters = ProcessMemory()
    counters.cb = ctypes.sizeof(counters)
    if handle:
        try:
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(handle),ctypes.byref(counters),counters.cb)
        finally:
            kernel.CloseHandle(handle)
    return status.available_physical,counters.working_set,counters.peak_working_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--blender",type=Path,default=Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"))
    parser.add_argument("--scenes",type=int,nargs="+",default=[0,1,2,3])
    parser.add_argument("--max-seconds",type=int,default=1800,help="Per isolated phase ceiling")
    parser.add_argument("--resume-saved",action="store_true",help="Continue a preserved complete scene without rebuilding")
    parser.add_argument("--min-free-gib",type=float,default=4.0,help="Recorded available RAM reserve (minimum 2 GiB)")
    parser.add_argument("--capture-batch",action="store_true",help="Keep the compact scene resident across remaining RGB views")
    args = parser.parse_args()
    if args.min_free_gib < 2:raise ValueError("Keep at least 2 GiB free RAM")
    root = args.root.resolve()
    if os.name != "nt":
        raise RuntimeError("This resource supervisor currently targets Windows")
    if any(i not in range(4) for i in args.scenes):
        raise ValueError("Scene index outside pilot")
    lock = root/"blender.lock"
    descriptor = os.open(lock,os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(descriptor,str(os.getpid()).encode())
    process = None
    try:
        for index in args.scenes:
            folder = root/f"scene_{index:02d}"
            if not (folder/"input.json").exists():raise FileNotFoundError(folder/"input.json")
            saved=(folder/"cultivation.blend").exists()
            if saved and not args.resume_saved:raise FileExistsError("Use --resume-saved for the preserved scene")
            previous=[]
            aggregate=folder/"resources.json"
            if aggregate.exists():
                old=json.loads(aggregate.read_text(encoding="utf-8"))
                if old.get("phases"):previous=old["phases"]
                else:
                    previous=[{"phase":"preserved_initial_attempt",**old}]
                    backup=folder/"resources_initial_attempt.json"
                    if not backup.exists():backup.write_bytes(aggregate.read_bytes())
            reports=list(previous)
            def run_phase(phase,script,extra):
                nonlocal process
                attempt=1
                label=phase
                while (folder/f"resources_{label}.json").exists() or (folder/f"{label}.log").exists():
                    attempt+=1;label=f"{phase}_attempt_{attempt}"
                phase_path=folder/f"resources_{label}.json"
                start=time.monotonic();samples=[];reason=None
                with (folder/f"{label}.log").open("x",encoding="utf-8") as log:
                    process=subprocess.Popen([str(args.blender),"--background","--factory-startup","--python-exit-code","1",
                        "--python",str(ROOT/"scripts"/script),"--","--scene-dir",str(folder),*extra],
                        stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    while process.poll() is None:
                        free,working,peak=memory(process.pid);elapsed=time.monotonic()-start
                        samples.append({"seconds":elapsed,"free_ram":free,"working_set":working,"peak_working_set":peak})
                        if free<args.min_free_gib*1024**3 or elapsed>args.max_seconds:
                            reason=f"ram_reserve_below_{args.min_free_gib:g}GiB" if free<args.min_free_gib*1024**3 else "phase_time_ceiling"
                            process.terminate();break
                        time.sleep(3)
                    code=process.wait()
                report={"phase":phase,"attempt":attempt,"min_free_gib":args.min_free_gib,"exit_code":code,"stop_reason":reason,"elapsed_seconds":time.monotonic()-start,
                        "peak_working_set_bytes":max((s["peak_working_set"] for s in samples),default=0),"samples":samples}
                phase_path.write_text(json.dumps(report,indent=2),encoding="utf-8");reports.append(report)
                aggregate.write_text(json.dumps({"scene":index,"exit_code":code,"stop_reason":reason,
                    "elapsed_seconds":sum(r["elapsed_seconds"] for r in reports),
                    "peak_working_set_bytes":max(r["peak_working_set_bytes"] for r in reports),
                    "cost_scope":"all_recorded_phases_including_preserved_failed_attempts","phases":reports},indent=2),encoding="utf-8")
                print(json.dumps({k:v for k,v in report.items() if k!="samples"}),flush=True)
                if code or reason:raise RuntimeError("Phase stopped; scene and evidence preserved")
            if not saved:run_phase("build","render_sparse_pilot.py",["--build-only"])
            if not (folder/"mesh_audit.json").exists():
                run_phase("audit","capture_saved_sparse.py",["--mode","audit"])
            plan=json.loads((folder/"capture_plan.json").read_text(encoding="utf-8"))
            pending=False
            for view in plan["views"]:
                name=view["name"]
                if (folder/name/"capture.json").exists():continue
                partial=folder/name
                if partial.exists():
                    if partial.resolve().parent != folder.resolve():raise ValueError("Capture outside scene")
                    diagnostics=folder/"diagnostics"
                    diagnostics.mkdir(exist_ok=True)
                    attempt=1
                    destination=diagnostics/f"{name}_incomplete_{attempt}"
                    while destination.exists():
                        attempt+=1;destination=diagnostics/f"{name}_incomplete_{attempt}"
                    partial.rename(destination)
                pending=True
                if not args.capture_batch:
                    run_phase("capture_"+name,"capture_saved_sparse.py",["--mode","capture","--camera",name])
            if pending and args.capture_batch:
                run_phase("capture_remaining","capture_saved_sparse.py",["--mode","capture","--all-missing"])
            (folder/"render_complete.json").write_text(json.dumps({"captures":[v["name"] for v in plan["views"]],
                "phase_isolation":True,"scene":index},indent=2),encoding="utf-8")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        os.close(descriptor)
        lock.unlink()


if __name__ == "__main__": main()
