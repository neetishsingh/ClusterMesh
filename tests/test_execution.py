"""Tests for task execution, checkpoint, and interrupt/resume."""

import threading
import time

import pytest

from mesh.execution import TaskContext, TaskExecutor, TaskInterrupted
from mesh.models.enums import TaskState
from mesh.models.task import TaskSpec
from mesh.recovery.checkpoint import CheckpointManager


class TestTaskContext:
    def test_set_progress_triggers_checkpoint(self):
        mgr = CheckpointManager()
        spec = TaskSpec(name="t", checkpoint=True, checkpoint_interval=0, total_work=100)
        ctx = TaskContext(task_spec=spec, checkpoint_manager=mgr, total_work=100)
        ctx.set_progress(50, offset=50)
        cp = mgr.load(spec.task_id)
        assert cp is not None
        assert cp.progress == 50
        assert cp.state_data["offset"] == 50

    def test_restore_from_checkpoint(self):
        mgr = CheckpointManager()
        spec = TaskSpec(name="t", checkpoint=True, total_work=1000)
        spec.progress = 650
        spec.state_data = {"offset": 650}
        mgr.save(spec, state_data={"offset": 650})

        ctx = TaskContext(task_spec=spec, checkpoint_manager=mgr, total_work=1000)
        assert ctx.restore_from_checkpoint()
        assert ctx.progress == 650
        assert ctx.get("offset") == 650

    def test_interrupt_raises_and_checkpoints(self):
        mgr = CheckpointManager()
        spec = TaskSpec(name="t", checkpoint=True, checkpoint_interval=0, total_work=100)
        ctx = TaskContext(task_spec=spec, checkpoint_manager=mgr, total_work=100)
        ctx.set_progress(40)
        ctx.interrupt.set()

        with pytest.raises(TaskInterrupted):
            ctx.set_progress(41)


class TestTaskExecutor:
    def test_runs_simple_function(self):
        executor = TaskExecutor()
        spec = TaskSpec(name="add", fn=lambda: None)

        def add():
            return 2 + 2

        assert executor.execute(add, spec) == 4
        assert spec.state == TaskState.COMPLETED

    def test_runs_with_context(self):
        executor = TaskExecutor()
        spec = TaskSpec(name="count", checkpoint=True, checkpoint_interval=0, total_work=10)

        def count(ctx: TaskContext):
            for i in range(int(ctx.progress), 10):
                ctx.set_progress(i + 1)
            return "done"

        assert executor.execute(count, spec) == "done"
        assert spec.progress == 10

    def test_interrupt_and_resume(self):
        mgr = CheckpointManager()
        executor = TaskExecutor(checkpoint_manager=mgr)
        spec = TaskSpec(name="long", checkpoint=True, checkpoint_interval=0, total_work=100)

        results = []

        def long_job(ctx: TaskContext):
            for i in range(int(ctx.progress), 100):
                ctx.set_progress(i + 1, step=i)
                if i == 30:
                    executor.interrupt(spec.task_id)
            results.append("finished")
            return "done"

        executor.execute(long_job, spec)
        assert spec.progress == 31
        assert "finished" not in results

        cp = mgr.load(spec.task_id)
        assert cp.progress == 31

        executor.clear_interrupt(spec.task_id)
        result = executor.execute(long_job, spec)
        assert result == "done"
        assert spec.progress == 100
