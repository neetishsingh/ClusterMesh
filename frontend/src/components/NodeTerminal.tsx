import { useEffect, useRef, useState } from "react";
import { api, NodeRow, ShellResult } from "@/api/client";
import { Terminal, Play, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ShellLine {
  kind: "prompt" | "stdout" | "stderr" | "meta";
  text: string;
}

export function NodeTerminal({ node }: { node: NodeRow }) {
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<ShellLine[]>([
    { kind: "meta", text: `Remote shell on ${node.hostname} — commands run in the worker's home directory.` },
  ]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, running]);

  async function runCommand(e: React.FormEvent) {
    e.preventDefault();
    const cmd = command.trim();
    if (!cmd || running) return;
    setRunning(true);
    setLines((prev) => [...prev, { kind: "prompt", text: `$ ${cmd}` }]);
    setCommand("");
    try {
      const res: ShellResult = await api.runNodeShell(node.node_id, cmd);
      setLines((prev) => {
        const next = [...prev];
        if (res.stdout) next.push({ kind: "stdout", text: res.stdout });
        if (res.stderr) next.push({ kind: "stderr", text: res.stderr });
        next.push({
          kind: "meta",
          text: res.ok
            ? `exit ${res.exit_code} · ${res.duration_seconds?.toFixed(2) ?? "?"}s`
            : `failed: ${res.error || res.message || "unknown error"}`,
        });
        return next;
      });
    } catch (err) {
      setLines((prev) => [
        ...prev,
        { kind: "stderr", text: err instanceof Error ? err.message : "Request failed" },
      ]);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="border-t border-slate-200 bg-slate-950">
      <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-2">
        <Terminal className="h-4 w-4 text-emerald-400" />
        <span className="text-xs font-medium text-slate-300">Remote Terminal — {node.hostname}</span>
      </div>
      <div className="max-h-64 overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed">
        {lines.map((line, i) => (
          <div
            key={i}
            className={cn(
              "whitespace-pre-wrap break-all",
              line.kind === "prompt" && "text-emerald-400",
              line.kind === "stdout" && "text-slate-200",
              line.kind === "stderr" && "text-red-400",
              line.kind === "meta" && "text-slate-500",
            )}
          >
            {line.text}
          </div>
        ))}
        {running && (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 className="h-3 w-3 animate-spin" /> running…
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form onSubmit={runCommand} className="flex gap-2 border-t border-slate-800 p-3">
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="pip install pyspark && java -version"
          disabled={running || !node.is_remote}
          className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-100 outline-none focus:border-emerald-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={running || !command.trim() || !node.is_remote}
          className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
          Run
        </button>
      </form>
      {!node.is_remote && (
        <p className="px-4 pb-3 text-[11px] text-amber-400">
          This node has no live agent connection — restart worker with clustermesh join.
        </p>
      )}
    </div>
  );
}
