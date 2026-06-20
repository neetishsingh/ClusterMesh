"""TCP relay for NAT traversal across sites (Tailscale-like overlay hop)."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


class TcpRelayServer:
    """
    Simple TCP port forwarder.

    Agents behind NAT connect to relay:6000 which forwards to local driver gRPC.
    Remote sites register relay endpoints in mesh config for cross-region routing.
    """

    def __init__(
        self,
        listen_address: str = "0.0.0.0:6000",
        target_address: str = "127.0.0.1:50050",
    ) -> None:
        host, port = listen_address.rsplit(":", 1)
        self.listen_host = host
        self.listen_port = int(port)
        thost, tport = target_address.rsplit(":", 1)
        self.target_host = thost
        self.target_port = int(tport)
        self._stop = threading.Event()
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self.connections = 0

    def start(self, blocking: bool = False) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.listen_host, self.listen_port))
        self._server.listen(128)
        self._server.settimeout(1.0)
        logger.info(
            "Mesh relay listening on %s:%d → %s:%d",
            self.listen_host,
            self.listen_port,
            self.target_host,
            self.target_port,
        )

        def serve() -> None:
            while not self._stop.is_set():
                try:
                    client, addr = self._server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    upstream = socket.create_connection(
                        (self.target_host, self.target_port), timeout=10
                    )
                except OSError as exc:
                    logger.warning("Relay upstream connect failed from %s: %s", addr, exc)
                    client.close()
                    continue
                self.connections += 1
                threading.Thread(
                    target=_pipe, args=(client, upstream), daemon=True
                ).start()
                threading.Thread(
                    target=_pipe, args=(upstream, client), daemon=True
                ).start()

        if blocking:
            serve()
        else:
            self._thread = threading.Thread(target=serve, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass

    @property
    def address(self) -> str:
        return f"{self.listen_host}:{self.listen_port}"


def main_relay() -> None:
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="ComputeMesh TCP relay")
    parser.add_argument("--listen", default="0.0.0.0:6000")
    parser.add_argument("--target", default="127.0.0.1:50050")
    args = parser.parse_args()
    relay = TcpRelayServer(args.listen, args.target)
    try:
        relay.start(blocking=True)
    except KeyboardInterrupt:
        relay.stop()
