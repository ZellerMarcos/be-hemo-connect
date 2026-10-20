import argparse
import ctypes
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.security.password import hash_password, password_hasher, verify_password


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def memory_snapshot() -> tuple[int, int]:
    if os.name != "nt":
        raise RuntimeError("Este benchmark de memoria foi preparado para Windows.")
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    ):
        raise ctypes.WinError()
    return counters.WorkingSetSize, counters.PeakWorkingSetSize


def verify_once(password: str, password_hash: str) -> float:
    started_at = time.perf_counter()
    if not verify_password(password, password_hash):
        raise RuntimeError("A verificacao Argon2 falhou durante o benchmark.")
    return (time.perf_counter() - started_at) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--operations", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.workers < 1 or args.operations < args.workers:
        raise ValueError("Use ao menos um worker e operations >= workers.")

    password = "Benchmark-Argon2-Only-Not-A-Credential"
    password_hash = hash_password(password)
    working_before, peak_before = memory_snapshot()
    wall_started_at = time.perf_counter()
    cpu_started_at = time.process_time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        latencies = list(executor.map(
            lambda _: verify_once(password, password_hash),
            range(args.operations),
        ))
    cpu_seconds = time.process_time() - cpu_started_at
    wall_seconds = time.perf_counter() - wall_started_at
    working_after, peak_after = memory_snapshot()

    result = {
        "argon2": {
            "hash_len": password_hasher.hash_len,
            "memory_cost_kib": password_hasher.memory_cost,
            "parallelism": password_hasher.parallelism,
            "salt_len": password_hasher.salt_len,
            "time_cost": password_hasher.time_cost,
            "type": "argon2id",
        },
        "concurrency": {
            "operations": args.operations,
            "workers": args.workers,
        },
        "cpu_seconds": round(cpu_seconds, 4),
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "maximum": round(max(latencies), 2),
            "minimum": round(min(latencies), 2),
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2),
        },
        "memory_bytes": {
            "peak_after": peak_after,
            "peak_increase": max(0, peak_after - peak_before),
            "working_after": working_after,
            "working_before": working_before,
        },
        "wall_seconds": round(wall_seconds, 4),
    }
    serialized = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
