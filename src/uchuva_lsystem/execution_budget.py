"""Effective runtime accounting; historical wall deadlines are not rewritten."""
import ctypes
import json
import os
from pathlib import Path
import time
import math


def _read_record(path):
    """Retry brief Windows sharing/write races; never substitute a zero budget."""
    for attempt in range(10):
        try:
            return json.loads(path.read_text())
        except (PermissionError, json.JSONDecodeError):
            if attempt == 9:
                raise
            time.sleep(.05)


def awake_seconds():
    """Windows unbiased uptime excludes system sleep/hibernation."""
    if os.name == 'nt':
        value = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
            raise OSError('Unable to read awake system clock')
        return value.value / 10_000_000
    return time.monotonic()


def remaining_seconds(root):
    root = Path(root)
    budget = _read_record(root/'effective_budget.json')
    used = float(budget['historical_execution_seconds'])
    sessions=[_read_record(p) for p in (root/'controller_sessions').glob('*.json')]
    for session in sessions:
        used+=session_elapsed(session)
    for path in (root/'execution_jobs').glob('*.json'):
        record = _read_record(path)
        covered=any(session['started_utc']<=record['started_utc'] and
                    (session['state']=='active' or record.get('ended_utc','9999')<=session['ended_utc'])
                    for session in sessions)
        if covered:continue
        used += float(record['awake_elapsed_seconds'])
    remaining = math.inf if budget['limit_seconds'] is None else max(0., float(budget['limit_seconds']) - used)
    if 'hard_deadline_unix' in budget:
        remaining = min(remaining, max(0., budget['hard_deadline_unix'] - time.time()))
    return remaining


def session_elapsed(session):
    if session['state']=='active' and os.name=='nt':
        return max(session['awake_elapsed_seconds'],awake_seconds()-session['awake_started_seconds'])
    return session['awake_elapsed_seconds']


def refresh_controller(root):
    """Persist the Windows awake clock for read-only checks in WSL children."""
    if os.name!='nt':return
    from .segmentation_cycles import write
    for path in (Path(root)/'controller_sessions').glob('*.json'):
        record=_read_record(path)
        if record['state']=='active':
            record['awake_elapsed_seconds']=session_elapsed(record)
            write(path,record)


def free_host_memory_gib():
    if os.name != 'nt':return None
    class MemoryStatus(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
            (name,ctypes.c_ulonglong) for name in ('total','free','page_total','page_free',
                                                'virtual_total','virtual_free','extended')]
    status=MemoryStatus();status.length=ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError('Unable to read host memory')
    return status.free/2**30
