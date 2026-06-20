"""Notebook cell execution on ComputeMesh workers."""

from __future__ import annotations

import io
import json
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any


def _build_namespace(language: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "__notebook__"}

    if language == "pyspark":
        try:
            from pyspark.sql import SparkSession

            spark = (
                SparkSession.builder.appName("ComputeMesh")
                .master("local[*]")
                .config("spark.ui.showConsoleProgress", "false")
                .getOrCreate()
            )
            namespace["spark"] = spark
            namespace["SparkSession"] = SparkSession
        except ImportError:
            namespace["spark"] = None
            namespace["_pyspark_error"] = (
                "PySpark not installed on this worker. "
                "Install with: pip install pyspark"
            )

    return namespace


def execute_code(code: str, language: str = "python") -> dict[str, Any]:
    """Run user code and capture stdout/stderr."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result_value: Any = None
    error: str | None = None

    namespace = _build_namespace(language)
    if language == "pyspark" and namespace.get("_pyspark_error"):
        return {
            "stdout": "",
            "stderr": namespace["_pyspark_error"],
            "error": namespace["_pyspark_error"],
            "result": None,
        }

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            compiled = compile(code, "<notebook>", "exec")
            exec(compiled, namespace)
            if "_result" in namespace:
                result_value = namespace["_result"]
    except Exception:
        error = traceback.format_exc()

    return {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "error": error,
        "result": _serialize(result_value),
    }


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value[:100]]
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in list(value.items())[:50]}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)
