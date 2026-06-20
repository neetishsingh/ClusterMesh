from __future__ import annotations

import re
from typing import Optional

from mesh.models.enums import ResourcePool


_UNITS = {
    "B": 1 / (1024**3),
    "KB": 1 / (1024**2),
    "MB": 1 / 1024,
    "GB": 1.0,
    "TB": 1024.0,
    "K": 1 / 1000,
    "M": 1.0,
    "G": 1000.0,
    "T": 1000_000.0,
}


def parse_bytes(value: str | float | int) -> float:
    """Parse '64GB', '128MB', or numeric GB into gigabytes."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.match(r"^([\d.]+)\s*([A-Za-z]+)$", value.strip())
    if not match:
        raise ValueError(f"Invalid size: {value!r}")
    num, unit = match.groups()
    unit = unit.upper()
    if unit not in _UNITS:
        raise ValueError(f"Unknown unit: {unit}")
    return float(num) * _UNITS[unit]


def parse_bandwidth(value: str | float | int) -> float:
    """Parse '10Gbps', '1Gbps', or numeric Gbps into gigabits per second."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.match(r"^([\d.]+)\s*([A-Za-z/]+)?$", value.strip())
    if not match:
        raise ValueError(f"Invalid bandwidth: {value!r}")
    num = float(match.group(1))
    unit = (match.group(2) or "Gbps").upper().replace("BPS", "").replace("BIT", "").replace("S", "")
    if unit in ("G", "GB", ""):
        return num
    if unit in ("M", "MB"):
        return num / 1000
    if unit in ("K", "KB"):
        return num / 1_000_000
    if unit in ("T", "TB"):
        return num * 1000
    raise ValueError(f"Unknown bandwidth unit: {unit}")


def parse_pool(value: str | ResourcePool | None) -> Optional[ResourcePool]:
    if value is None:
        return None
    if isinstance(value, ResourcePool):
        return value
    return ResourcePool(value.lower())
