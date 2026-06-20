"""Built-in tasks available on every agent."""

from __future__ import annotations

import json

from mesh import task
from mesh.execution import TaskContext
from mesh.notebook.runner import execute_code
from mesh.tasks.registry import register


@task(name="builtin.counter", cpu=1, checkpoint=True, checkpoint_interval=0, total_work=1000)
def counter(ctx: TaskContext):
    target = int(ctx.total_work)
    for i in range(int(ctx.progress), target):
        ctx.set_progress(i + 1, count=i + 1)
    return {"count": target}


@task(name="notebook.exec", cpu=1, ram="512MB", checkpoint=False, total_work=1)
def notebook_exec(ctx: TaskContext):
    """Execute notebook cell code passed via state_data."""
    code = ctx.state_data.get("code", "")
    language = ctx.state_data.get("language", "python")
    if not code.strip():
        return {"stdout": "", "stderr": "", "error": "Empty cell", "result": None}
    output = execute_code(code, language=language)
    ctx.set_progress(1)
    return output


register("builtin.counter", counter.fn)
register("notebook.exec", notebook_exec.fn)
