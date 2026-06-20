import { useEffect, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { useShell } from "@/components/Layout";
import { api, LogRow } from "@/api/client";
import { formatTime, logLevelColor, cn } from "@/lib/utils";
import { Filter, Download } from "lucide-react";

export function LogsPage() {
  const { cluster, connected, refresh, lastEvent } = useShell();
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [level, setLevel] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const loadLogs = async () => {
    const data = await api.logs({
      limit: 500,
      level: level || undefined,
      source: source || undefined,
      q: search || undefined,
    });
    setLogs(data);
  };

  useEffect(() => {
    loadLogs().catch(() => {});
    const id = setInterval(() => loadLogs().catch(() => {}), 5000);
    return () => clearInterval(id);
  }, [level, source, search]);

  useEffect(() => {
    if (lastEvent && autoScroll) {
      setLogs((prev) => {
        const row = lastEvent as unknown as LogRow;
        if (prev.some((l) => l.id === row.id)) return prev;
        return [...prev.slice(-499), row];
      });
    }
  }, [lastEvent, autoScroll]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  function exportLogs() {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clustermesh-logs-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <Header
        title="Logs"
        subtitle="Live event stream from driver, agents, and scheduler"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); loadLogs(); }}
        actions={
          <button type="button" onClick={exportLogs} className="btn-secondary !py-1.5 !text-xs">
            <Download className="h-3.5 w-3.5" />
            Export
          </button>
        }
      />
      <div className="flex flex-1 flex-col p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-mesh-500"
          >
            <option value="">All levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
          </select>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-mesh-500"
          >
            <option value="">All sources</option>
            <option value="driver">driver</option>
            <option value="platform">platform</option>
            <option value="scheduler">scheduler</option>
            <option value="cluster">cluster</option>
            <option value="jobs">jobs</option>
            <option value="preemption">preemption</option>
            <option value="libraries">libraries</option>
          </select>
          <input
            type="search"
            placeholder="Search messages…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-mesh-500"
          />
          <label className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded border-slate-300"
            />
            Auto-scroll
          </label>
          <span className="text-xs text-slate-400">{logs.length} events</span>
        </div>

        <div className="card log-scroll flex-1 overflow-auto font-mono text-xs">
          <table className="w-full">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                <th className="table-head w-44">Time</th>
                <th className="table-head w-16">Level</th>
                <th className="table-head w-24">Source</th>
                <th className="table-head">Message</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50/80">
                  <td className="table-cell whitespace-nowrap text-slate-400">
                    {formatTime(log.timestamp)}
                  </td>
                  <td className={cn("table-cell font-semibold", logLevelColor(log.level))}>
                    {log.level}
                  </td>
                  <td className="table-cell text-slate-500">{log.source}</td>
                  <td className="table-cell text-slate-700">
                    {log.message}
                    {Object.keys(log.metadata || {}).length > 0 && (
                      <span className="ml-2 text-slate-400">
                        {JSON.stringify(log.metadata)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {!logs.length && (
                <tr>
                  <td colSpan={4} className="table-cell py-16 text-center text-slate-400">
                    No log events yet — start the platform to see live activity
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div ref={bottomRef} />
        </div>
      </div>
    </>
  );
}
