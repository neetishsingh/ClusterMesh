"""Tests for SQLite state store."""

import tempfile
from pathlib import Path

from mesh.models.job import Job, JobState
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import Checkpoint
from mesh.state import SQLiteStateStore


class TestSQLiteStateStore:
    def test_job_roundtrip(self):
        store = SQLiteStateStore(":memory:")
        job = Job(name="etl", state=JobState.RUNNING, task_ids=["t1"])
        store.save_job(job)
        loaded = store.load_job(job.job_id)
        assert loaded.name == "etl"
        assert loaded.state == JobState.RUNNING

    def test_task_roundtrip(self):
        store = SQLiteStateStore(":memory:")
        task = TaskSpec(name="process", progress=650, total_work=1000)
        store.save_task(task)
        loaded = store.load_task(task.task_id)
        assert loaded.progress == 650
        assert loaded.name == "process"

    def test_checkpoint_roundtrip(self):
        store = SQLiteStateStore(":memory:")
        cp = Checkpoint(task_id="t1", progress=650, state_data={"offset": 650})
        store.save_checkpoint(cp)
        loaded = store.load_checkpoint("t1")
        assert loaded.progress == 650
        assert loaded.state_data["offset"] == 650

    def test_leadership_election(self):
        store = SQLiteStateStore(":memory:")
        assert store.try_acquire_leadership("driver-1", 1, 10.0)
        assert store.get_leader() == ("driver-1", 1)
        assert not store.try_acquire_leadership("driver-2", 1, 10.0)
        assert store.renew_leadership("driver-1", 1, 10.0)
        assert store.try_acquire_leadership("driver-2", 2, 10.0)

    def test_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            store = SQLiteStateStore(path)
            job = Job(name="disk-test")
            store.save_job(job)
            store.close()

            store2 = SQLiteStateStore(path)
            assert store2.load_job(job.job_id).name == "disk-test"
            store2.close()
