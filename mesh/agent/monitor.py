from __future__ import annotations

from dataclasses import dataclass
import platform
import re
import socket
import time
from typing import Any

from mesh.agent.host_metrics import collect_host_metrics

try:
    import psutil
except ImportError:  # pragma: no cover - tested with mock
    psutil = None  # type: ignore


@dataclass
class ResourceSnapshot:
    cpu_cores_total: int
    cpu_cores_free: float
    ram_gb_total: float
    ram_gb_free: float
    gpu_count: int = 0
    vram_gb_free: float = 0.0
    cuda_version: str | None = None
    network_gbps: float = 1.0
    battery_pct: float | None = None
    cpu_utilization: float = 0.0
    user_active: bool = False
    cpu_cores_physical: int = 0
    host_metrics_json: str = ""


class ResourceMonitor:
    """Collects live resource metrics from the host OS."""

    def __init__(
        self,
        cpu_reserve_pct: float = 0.15,
        *,
        ema_alpha: float = 0.25,
        min_sample_interval: float = 1.0,
    ) -> None:
        self.cpu_reserve_pct = cpu_reserve_pct
        self.ema_alpha = ema_alpha
        self.min_sample_interval = min_sample_interval
        self._cpu_ema: float | None = None
        self._cpu_primed = False
        self._last_sample_at = 0.0
        self._last_snapshot: ResourceSnapshot | None = None
        self._last_cpu_times: Any | None = None

    def snapshot(self, *, force: bool = False) -> ResourceSnapshot:
        now = time.monotonic()
        if (
            not force
            and self._last_snapshot is not None
            and now - self._last_sample_at < self.min_sample_interval
        ):
            return self._last_snapshot

        if psutil is None:
            self._last_snapshot = ResourceSnapshot(
                cpu_cores_total=4,
                cpu_cores_free=3.0,
                ram_gb_total=16.0,
                ram_gb_free=8.0,
                cpu_cores_physical=4,
            )
            self._last_sample_at = now
            return self._last_snapshot

        cpu_logical = psutil.cpu_count(logical=True) or 1
        cpu_physical = psutil.cpu_count(logical=False) or cpu_logical
        cpu_pct, cpu_times = self._sample_cpu_utilization()
        free_cores = max(0.0, cpu_logical * (1.0 - cpu_pct - self.cpu_reserve_pct))

        mem = psutil.virtual_memory()
        ram_total = mem.total / (1024**3)
        ram_free = mem.available / (1024**3)

        battery = None
        if hasattr(psutil, "sensors_battery"):
            bat = psutil.sensors_battery()
            if bat is not None:
                battery = bat.percent

        user_active = self._detect_user_active(cpu_times, cpu_pct)
        gpu_count, vram, cuda = self._detect_gpu()

        host_detail = collect_host_metrics(
            cpu_utilization=cpu_pct,
            cpu_times=cpu_times,
        )
        if gpu_count and host_detail.get("gpu", {}).get("count", 0) == 0:
            host_detail["gpu"] = {"count": gpu_count, "name": cuda or "GPU", "names": [cuda or "GPU"]}

        import json

        self._last_snapshot = ResourceSnapshot(
            cpu_cores_total=cpu_logical,
            cpu_cores_physical=cpu_physical,
            cpu_cores_free=free_cores,
            ram_gb_total=ram_total,
            ram_gb_free=ram_free,
            gpu_count=max(gpu_count, host_detail.get("gpu", {}).get("count", 0)),
            vram_gb_free=vram,
            cuda_version=cuda,
            battery_pct=battery,
            cpu_utilization=cpu_pct,
            user_active=user_active,
            host_metrics_json=json.dumps(host_detail, separators=(",", ":")),
        )
        self._last_sample_at = now
        return self._last_snapshot

    def _sample_cpu_utilization(self) -> tuple[float, Any | None]:
        if psutil is None:
            return 0.0, None

        cpu_times = None
        if not self._cpu_primed:
            psutil.cpu_percent(interval=None)
            psutil.cpu_times_percent(interval=None)
            raw = psutil.cpu_percent(interval=0.5) / 100.0
            cpu_times = psutil.cpu_times_percent(interval=None)
            self._cpu_primed = True
        else:
            raw = psutil.cpu_percent(interval=None) / 100.0
            cpu_times = psutil.cpu_times_percent(interval=None)

        if self._cpu_ema is None:
            self._cpu_ema = raw
        else:
            self._cpu_ema = self.ema_alpha * raw + (1.0 - self.ema_alpha) * self._cpu_ema
        self._last_cpu_times = cpu_times
        return self._cpu_ema, cpu_times

    def _detect_user_active(self, cpu_times: Any | None, cpu_utilization: float) -> bool:
        if platform.system() == "Darwin":
            idle_seconds = _darwin_idle_seconds()
            if idle_seconds is not None:
                return idle_seconds < 60.0
        if cpu_times is not None:
            try:
                return getattr(cpu_times, "idle", 100.0) < 30.0
            except Exception:
                pass
        return cpu_utilization > 0.5

    def _detect_gpu(self) -> tuple[int, float, str | None]:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.free,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                vram = float(parts[1]) / 1024 if len(parts) > 1 else 0.0
                cuda = parts[2].split(".")[0] if len(parts) > 2 else None
                return 1, vram, cuda
        except Exception:
            pass
        return 0, 0.0, None


def _darwin_idle_seconds() -> float | None:
    """Seconds since last user input (Activity Monitor idle semantics)."""
    try:
        import subprocess

        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out.stdout)
        if m:
            return int(m.group(1)) / 1_000_000_000.0
    except Exception:
        pass
    return None


def get_hostname() -> str:
    return socket.gethostname()


def get_os_name() -> str:
    return f"{platform.system()} {platform.release()}"
