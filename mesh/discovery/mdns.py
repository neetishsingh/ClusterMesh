"""Local network discovery via mDNS/DNS-SD."""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_computemesh._tcp.local."
SERVICE_NAME = "ComputeMesh Driver"


@dataclass
class DriverRecord:
    host: str
    grpc_port: int
    api_port: int
    site: str = "default"

    @property
    def grpc_address(self) -> str:
        return f"{self.host}:{self.grpc_port}"


class DriverAdvertiser:
    """Advertise the driver on the local network."""

    def __init__(
        self,
        grpc_port: int,
        api_port: int,
        site: str = "default",
        host: str | None = None,
    ) -> None:
        self.grpc_port = grpc_port
        self.api_port = api_port
        self.site = site
        self.host = host or _local_ip()
        self._zeroconf = None
        self._info = None

    def start(self) -> None:
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError as exc:
            raise ImportError(
                "mDNS requires zeroconf — pip install clustermesh[discovery]"
            ) from exc

        props = {
            b"grpc_port": str(self.grpc_port).encode(),
            b"api_port": str(self.api_port).encode(),
            b"site": self.site.encode(),
        }
        self._info = ServiceInfo(
            SERVICE_TYPE,
            f"{SERVICE_NAME}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(self.host)],
            port=self.grpc_port,
            properties=props,
        )
        self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self._zeroconf.register_service(self._info)
        logger.info(
            "mDNS advertising driver at %s:%d (site=%s)",
            self.host,
            self.grpc_port,
            self.site,
        )

    def stop(self) -> None:
        if self._zeroconf and self._info:
            self._zeroconf.unregister_service(self._info)
            self._zeroconf.close()


class DriverBrowser:
    """Browse for drivers on the local network."""

    def __init__(self, on_found: Optional[Callable[[DriverRecord], None]] = None) -> None:
        self._on_found = on_found
        self._records: list[DriverRecord] = []
        self._zeroconf = None
        self._browser = None

    def start(self) -> None:
        try:
            from zeroconf import ServiceBrowser, Zeroconf
        except ImportError as exc:
            raise ImportError(
                "mDNS requires zeroconf — pip install clustermesh[discovery]"
            ) from exc

        browser = self

        class Listener:
            def add_service(inner, zc, type_, name) -> None:
                info = zc.get_service_info(type_, name)
                if not info:
                    return
                host = socket.inet_ntoa(info.addresses[0])
                props = {k.decode(): v.decode() for k, v in info.properties.items()}
                rec = DriverRecord(
                    host=host,
                    grpc_port=int(props.get("grpc_port", info.port)),
                    api_port=int(props.get("api_port", 8080)),
                    site=props.get("site", "default"),
                )
                browser._records.append(rec)
                if browser._on_found:
                    browser._on_found(rec)

            def remove_service(inner, zc, type_, name) -> None:
                pass

            def update_service(inner, zc, type_, name) -> None:
                pass

        self._zeroconf = Zeroconf()
        self._browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, Listener())

    def stop(self) -> None:
        if self._zeroconf:
            self._zeroconf.close()

    @property
    def records(self) -> list[DriverRecord]:
        return list(self._records)


def discover_driver(timeout: float = 5.0) -> Optional[DriverRecord]:
    """Block until a driver is found or timeout."""
    import time

    found: list[DriverRecord] = []
    browser = DriverBrowser(on_found=lambda r: found.append(r))
    browser.start()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and not found:
            time.sleep(0.2)
    finally:
        browser.stop()
    return found[0] if found else None


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
