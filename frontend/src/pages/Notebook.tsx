import { useCallback, useState } from "react";
import { Header } from "@/components/Header";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import {
  Play,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  BookOpen,
  Server,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Language = "python" | "pyspark";

interface Cell {
  id: string;
  language: Language;
  code: string;
  output: string | null;
  error: string | null;
  stderr: string | null;
  status: "idle" | "running" | "done" | "error";
  executionCount: number | null;
  collapsed: boolean;
}

const DEFAULT_PYTHON = `# Runs on a ComputeMesh worker (mesh-agent)
# Available: standard Python 3.11+

from mesh import task, submit

print("Hello from ComputeMesh")
print(f"Workers connected — code executes on real cluster nodes")
`;

const DEFAULT_PYSPARK = `# PySpark cell — requires pyspark on the worker
# pip install pyspark  (on each agent machine)

from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("ComputeMesh").master("local[*]").getOrCreate()

data = [("Alice", 34), ("Bob", 45), ("Carol", 28)]
df = spark.createDataFrame(data, ["name", "age"])
df.show()
print(f"Rows: {df.count()}")
`;

function newCell(language: Language = "python"): Cell {
  return {
    id: crypto.randomUUID(),
    language,
    code: language === "pyspark" ? DEFAULT_PYSPARK : DEFAULT_PYTHON,
    output: null,
    error: null,
    stderr: null,
    status: "idle",
    executionCount: null,
    collapsed: false,
  };
}

export function NotebookPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: nbStatus, reload: reloadStatus } = usePolling(() => api.notebookStatus(), 5000);
  const [cells, setCells] = useState<Cell[]>([newCell()]);
  const [runningAll, setRunningAll] = useState(false);

  const updateCell = useCallback((id: string, patch: Partial<Cell>) => {
    setCells((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }, []);

  async function runCell(cell: Cell) {
    updateCell(cell.id, { status: "running", output: null, error: null, stderr: null });
    try {
      const res = await api.executeNotebook(cell.code, cell.language, "mesh");
      const count = (cell.executionCount ?? 0) + 1;
      const modeLabel = res.mode === "mesh" ? `mesh:${res.node}` : "driver (local)";
      updateCell(cell.id, {
        status: res.error ? "error" : "done",
        output: [
          res.stdout,
          res.result != null ? `\n→ ${JSON.stringify(res.result, null, 2)}` : "",
          res.mode ? `\n— ran on ${modeLabel}` : "",
        ]
          .filter(Boolean)
          .join("\n"),
        stderr: res.stderr || null,
        error: res.error || null,
        executionCount: count,
      });
      refresh();
    } catch (e) {
      updateCell(cell.id, {
        status: "error",
        error: e instanceof Error ? e.message : "Execution failed",
      });
    }
  }

  async function runAll() {
    setRunningAll(true);
    for (const cell of cells) {
      await runCell(cell);
    }
    setRunningAll(false);
  }

  const meshWorkers = nbStatus?.workers_available ?? 0;
  const localAvailable = nbStatus?.local_available ?? true;

  return (
    <>
      <Header
        title="Notebook"
        subtitle="Databricks-style workspace — runs on mesh workers or locally on the driver"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reloadStatus(); }}
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-600 md:flex">
              <Server className="h-3.5 w-3.5" />
              {meshWorkers > 0
                ? `${meshWorkers} mesh worker${meshWorkers !== 1 ? "s" : ""}`
                : localAvailable
                  ? "driver (local)"
                  : "no executor"}
            </span>
            <button type="button" onClick={runAll} disabled={runningAll} className="btn-primary !py-1.5 !text-xs">
              <Play className="h-3.5 w-3.5" />
              Run All
            </button>
          </div>
        }
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {meshWorkers === 0 && localAvailable && (
          <div className="border-b border-slate-200 bg-slate-50 px-6 py-2.5 text-sm text-slate-600">
            No mesh workers ready — cells run locally on the driver. Start{" "}
            <code className="rounded bg-slate-100 px-1">mesh-agent</code> on another machine to
            offload work. See <strong>Cluster → Join instructions</strong>.
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {cells.map((cell) => (
            <div key={cell.id} className="border-b border-slate-200">
              {/* Cell toolbar */}
              <div className="flex items-center gap-2 bg-slate-50/80 px-4 py-1.5">
                <button
                  type="button"
                  onClick={() => updateCell(cell.id, { collapsed: !cell.collapsed })}
                  className="text-slate-400 hover:text-slate-600"
                >
                  {cell.collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                <span className="w-8 text-right font-mono text-xs text-slate-400">
                  [{cell.executionCount ?? " "}]
                </span>
                <select
                  value={cell.language}
                  onChange={(e) =>
                    updateCell(cell.id, {
                      language: e.target.value as Language,
                      code: e.target.value === "pyspark" ? DEFAULT_PYSPARK : DEFAULT_PYTHON,
                    })
                  }
                  className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs"
                >
                  <option value="python">Python</option>
                  <option value="pyspark">PySpark</option>
                </select>
                <button
                  type="button"
                  onClick={() => runCell(cell)}
                  disabled={cell.status === "running"}
                  className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-mesh-600 hover:bg-mesh-50"
                >
                  <Play className="h-3 w-3" />
                  {cell.status === "running" ? "Running…" : "Run"}
                </button>
                <button
                  type="button"
                  onClick={() => setCells((p) => p.filter((c) => c.id !== cell.id))}
                  disabled={cells.length === 1}
                  className="ml-auto text-slate-400 hover:text-red-500"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              {!cell.collapsed && (
                <>
                  <textarea
                    value={cell.code}
                    onChange={(e) => updateCell(cell.id, { code: e.target.value })}
                    spellCheck={false}
                    className="w-full resize-y border-0 bg-white px-6 py-3 font-mono text-sm leading-relaxed text-slate-800 outline-none focus:ring-2 focus:ring-inset focus:ring-mesh-500/30"
                    rows={Math.max(6, cell.code.split("\n").length + 1)}
                    placeholder="# Write Python or PySpark code…"
                  />
                  {(cell.output || cell.error || cell.stderr) && (
                    <div
                      className={cn(
                        "border-t border-slate-100 px-6 py-3 font-mono text-xs",
                        cell.error ? "bg-red-50 text-red-800" : "bg-slate-50 text-slate-700",
                      )}
                    >
                      {cell.stderr && (
                        <pre className="mb-2 whitespace-pre-wrap text-amber-700">{cell.stderr}</pre>
                      )}
                      {cell.output && <pre className="whitespace-pre-wrap">{cell.output}</pre>}
                      {cell.error && <pre className="mt-2 whitespace-pre-wrap">{cell.error}</pre>}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="flex items-center gap-2 border-t border-slate-200 bg-white px-4 py-2">
          <button
            type="button"
            onClick={() => setCells((p) => [...p, newCell("python")])}
            className="btn-secondary !py-1.5 !text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            Code cell
          </button>
          <button
            type="button"
            onClick={() => setCells((p) => [...p, newCell("pyspark")])}
            className="btn-secondary !py-1.5 !text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            PySpark cell
          </button>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
            <BookOpen className="h-3.5 w-3.5" />
            ComputeMesh Notebook
          </span>
        </div>
      </div>
    </>
  );
}
