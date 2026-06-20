"""Run shell commands on agent hosts (remote terminal)."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

MAX_OUTPUT = 65536


def run_shell_command(
    command: str,
    working_dir: str = "",
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    cmd = command.strip()
    if not cmd:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "message": "empty command",
            "duration_seconds": 0.0,
        }

    timeout = max(1, min(int(timeout_seconds or 60), 300))
    cwd = working_dir.strip() or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        stdout = _truncate(result.stdout or "")
        stderr = _truncate(result.stderr or "")
        ok = result.returncode == 0
        return {
            "ok": ok,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "message": "completed" if ok else f"exit {result.returncode}",
            "duration_seconds": round(duration, 3),
            "cwd": cwd,
        }
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": _truncate(exc.stdout or ""),
            "stderr": _truncate(exc.stderr or ""),
            "message": f"timed out after {timeout}s",
            "duration_seconds": round(duration, 3),
            "cwd": cwd,
        }
    except Exception as exc:
        duration = time.time() - start
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "message": str(exc),
            "duration_seconds": round(duration, 3),
            "cwd": cwd,
        }


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n… truncated ({len(text)} chars total)"
