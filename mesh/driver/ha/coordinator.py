from __future__ import annotations

import logging
from typing import Optional

from mesh.driver.ha.election import LeaderElection
from mesh.driver.job_manager import JobManager
from mesh.state.store import StateStore

logger = logging.getLogger(__name__)


class HADriverCoordinator:
    """Leader election + failover resume for JobManager."""

    def __init__(
        self,
        manager: JobManager,
        store: StateStore,
        election: Optional[LeaderElection] = None,
    ) -> None:
        self.manager = manager
        self.store = store
        self.election = election or LeaderElection(store)
        self.manager.state_store = store
        self.manager.leadership_check = lambda: self.is_leader
        self.election.on_leadership_change(self._on_leadership)

    def start(self) -> None:
        self.election.start()
        if self.election.is_leader:
            self.manager.resume_from_store(self.store)

    def stop(self) -> None:
        self.election.stop()

    @property
    def is_leader(self) -> bool:
        return self.election.is_leader

    def _on_leadership(self, is_leader: bool) -> None:
        if is_leader:
            logger.info("Leadership acquired — loading durable state")
            self.manager.resume_from_store(self.store)
