"""Host-level metrics aligned with macOS Activity Monitor where possible."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import time
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

_PROCESS_PRIME = False
_PROCESS_CACHE: list[dict[str, Any]] = []
_PROCESS_CACHE_AT = 0.0
_GPU_CACHE: dict[str, Any] | None = None


def collect_host_metrics(
    *,
    cpu_utilization: float,
    cpu_times: Any | None = None,
    process_interval: float = 3.0,
) -> dict[str, Any]:
    """Build Activity Monitor-style host detail payload."""
    if psutil is None:
        return {"platform": platform.system(), "cpu": {"utilization_pct": round(cpu_utilization * 100, 1)}}

    logical = psutil.cpu_count(logical=True) or 1
    physical = psutil.cpu_count(logical=False) or logical
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    cpu_block: dict[str, Any] = {
        "logical_cores": logical,
        "physical_cores": physical,
        "brand": _cpu_brand(),
        "utilization_pct": round(cpu_utilization * 100, 1),
        "user_pct": 0.0,
        "system_pct": 0.0,
        "idle_pct": 100.0,
        "load_avg": list(getattr(psutil, "getloadavg", lambda: (0.0, 0.0, 0.0))()),
    }
    if cpu_times is not None:
        cpu_block.update(
            {
                "user_pct": round(getattr(cpu_times, "user", 0.0), 1),
                "system_pct": round(getattr(cpu_times, "system", 0.0), 1),
                "idle_pct": round(getattr(cpu_times, "idle", 100.0), 1),
            }
        )

    memory_block: dict[str, Any] = {
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent": round(mem.percent, 1),
        "swap_gb": round(swap.used / (1024**3), 2),
    }
    if platform.system() == "Darwin":
        memory_block.update(_darwin_memory_breakdown())

    proc_block = _process_stats(process_interval=process_interval)
    gpu_block = _gpu_info()

    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "cpu": cpu_block,
        "memory": memory_block,
        "processes": proc_block,
        "gpu": gpu_block,
        "collected_at": time.time(),
    }


def host_metrics_json(**kwargs) -> str:
    return json.dumps(collect_host_metrics(**kwargs), separators=(",", ":"))


def _cpu_brand() -> str:
    if platform.system() != "Darwin":
        return platform.processor() or platform.machine()
    try:
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        brand = out.stdout.strip()
        if brand:
            return brand
    except Exception:
        pass
    return platform.machine()


def _darwin_memory_breakdown() -> dict[str, float]:
    """Parse vm_stat for wired/compressed pages (Activity Monitor categories)."""
    page_size = 4096
    try:
        page_size = int(
            subprocess.run(
                ["sysctl", "-n", "hw.pagesize"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout.strip()
        )
    except Exception:
        pass

    pages: dict[str, int] = {}
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=2, check=False)
        for line in out.stdout.splitlines():
            m = re.match(r"Pages\s+(.+?):\s+(\d+)\.", line.strip())
            if m:
                pages[m.group(1).lower().replace(" ", "_")] = int(m.group(2))
    except Exception:
        return {}

    def gb(key: str) -> float:
        return round(pages.get(key, 0) * page_size / (1024**3), 2)

    wired = gb("wired_down")
    compressed = gb("occupied_by_compressor")
    active = gb("active")
    inactive = gb("inactive")
    free = gb("free")
    return {
        "wired_gb": wired,
        "compressed_gb": compressed,
        "active_gb": active,
        "inactive_gb": inactive,
        "free_gb": free,
        "app_gb": round(active + inactive, 2),
    }


def _process_stats(*, process_interval: float) -> dict[str, Any]:
    global _PROCESS_PRIME, _PROCESS_CACHE, _PROCESS_CACHE_AT

    total_procs = 0
    total_threads = 0
    try:
        for proc in psutil.process_iter(["num_threads"]):
            info = proc.info
            total_procs += 1
            total_threads += info.get("num_threads") or 0
    except Exception:
        pass

    now = time.monotonic()
    if now - _PROCESS_CACHE_AT < process_interval and _PROCESS_CACHE:
        return {
            "total": total_procs,
            "threads_total": total_threads,
            "top": _PROCESS_CACHE,
        }

    top: list[dict[str, Any]] = []
    try:
        candidates = []
        for proc in psutil.process_iter(["pid", "name", "num_threads"]):
            try:
                if not _PROCESS_PRIME:
                    proc.cpu_percent(interval=None)
                candidates.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        _PROCESS_PRIME = True

        for proc in candidates:
            try:
                cpu_pct = proc.cpu_percent(interval=None)
                mem = proc.memory_info()
                top.append(
                    {
                        "pid": proc.pid,
                        "name": proc.info.get("name") or proc.name(),
                        "cpu_pct": round(cpu_pct, 1),
                        "threads": proc.info.get("num_threads") or proc.num_threads(),
                        "memory_mb": round(mem.rss / (1024**2), 1),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        top.sort(key=lambda p: p["cpu_pct"], reverse=True)
        _PROCESS_CACHE = top[:12]
        _PROCESS_CACHE_AT = now
    except Exception:
        pass

    return {
        "total": total_procs,
        "threads_total": total_threads,
        "top": _PROCESS_CACHE,
    }


def _gpu_info() -> dict[str, Any]:
    global _GPU_CACHE
    if _GPU_CACHE is not None:
        return _GPU_CACHE

    if platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            names = re.findall(r"Chipset Model:\s*(.+)", out.stdout)
            if names:
                _GPU_CACHE = {"count": len(names), "names": names, "name": names[0]}
                return _GPU_CACHE
        except Exception:
            pass

    _GPU_CACHE = {"count": 0, "names": [], "name": ""}
    return _GPU_CACHE
