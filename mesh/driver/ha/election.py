from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable, Optional

from mesh.state.store import StateStore

logger = logging.getLogger(__name__)


class LeaderElection:
    """
    Lease-based leader election backed by shared StateStore.

    Simulates Raft leader election — one writer (leader) at a time.
    """

    def __init__(
        self,
        store: StateStore,
        driver_id: Optional[str] = None,
        lease_seconds: float = 10.0,
        renew_interval: float = 3.0,
    ) -> None:
        self.store = store
        self.driver_id = driver_id or f"driver-{uuid.uuid4().hex[:8]}"
        self.lease_seconds = lease_seconds
        self.renew_interval = renew_interval
        self.term = 0
        self.is_leader = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_leadership: list[Callable[[bool], None]] = []

    def on_leadership_change(self, callback: Callable[[bool], None]) -> None:
        self._on_leadership.append(callback)

    def start(self) -> None:
        self._try_become_leader()
        self._thread = threading.Thread(target=self._renew_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.is_leader = False

    def _try_become_leader(self) -> None:
        if self._stop.is_set():
            return
        self.term += 1
        acquired = self.store.try_acquire_leadership(
            self.driver_id, self.term, self.lease_seconds
        )
        if acquired != self.is_leader:
            self.is_leader = acquired
            for cb in self._on_leadership:
                cb(self.is_leader)
        if acquired:
            logger.info("Driver %s elected leader (term %d)", self.driver_id, self.term)

    def _renew_loop(self) -> None:
        while not self._stop.is_set():
            if self.is_leader:
                ok = self.store.renew_leadership(
                    self.driver_id, self.term, self.lease_seconds
                )
                if not ok:
                    self.is_leader = False
                    for cb in self._on_leadership:
                        cb(False)
                    self._try_become_leader()
            else:
                self._try_become_leader()
            self._stop.wait(self.renew_interval)

    def current_leader(self) -> Optional[tuple[str, int]]:
        return self.store.get_leader()
