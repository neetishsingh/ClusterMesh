"""Notebook execution tests."""

from mesh.notebook.runner import execute_code


class TestNotebookRunner:
    def test_python_stdout(self):
        out = execute_code('print("hello")', "python")
        assert "hello" in out["stdout"]
        assert out["error"] is None

    def test_python_error(self):
        out = execute_code("1/0", "python")
        assert out["error"] is not None

    def test_pyspark_without_install(self):
        out = execute_code("print(1)", "pyspark")
        # Either runs or reports pyspark missing
        assert out["stdout"] or out["stderr"] or out["error"]
