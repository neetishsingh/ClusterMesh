from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
import sys


@dataclass
class InstalledLibrary:
    name: str
    version: str


@dataclass
class LibraryManager:
    """Tracks and installs Python packages via pip."""

    _installed: dict[str, InstalledLibrary] = field(default_factory=dict, repr=False)

    def scan(self) -> list[InstalledLibrary]:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=freeze"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            libs = []
            for line in result.stdout.strip().split("\n"):
                if "==" in line:
                    name, version = line.split("==", 1)
                    lib = InstalledLibrary(name=name.lower(), version=version)
                    self._installed[lib.name] = lib
                    libs.append(lib)
            return libs
        except Exception:
            return list(self._installed.values())

    def install(self, package_name: str, version: str = "") -> tuple[InstalledLibrary, str]:
        ver = version.strip()
        if ver.lower() in ("latest", "*", ""):
            spec = package_name
        else:
            spec = f"{package_name}=={ver}"
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", spec],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        log = "\n".join(filter(None, [result.stdout.strip(), result.stderr.strip()]))
        if result.returncode != 0:
            raise RuntimeError(log or f"pip install failed (exit {result.returncode})")
        self.scan()
        installed = self._installed.get(package_name.lower())
        lib = installed or InstalledLibrary(
            name=package_name.lower(),
            version=ver or "latest",
        )
        self._installed[lib.name] = lib
        return lib, log

    def list_names(self) -> list[str]:
        if not self._installed:
            self.scan()
        return sorted(self._installed.keys())

    def has(self, name: str) -> bool:
        if not self._installed:
            self.scan()
        return name.lower() in self._installed
