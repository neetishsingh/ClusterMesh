import { useEffect, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api, InstallLibraryResult, LogRow } from "@/api/client";
import { Package, Plus, CheckCircle2, XCircle, Terminal } from "lucide-react";
import { cn, logLevelColor } from "@/lib/utils";

export function LibrariesPage() {
  const { cluster, connected, refresh, lastEvent } = useShell();
  const { data: libraries, reload } = usePolling(() => api.libraries(), 10000);
  const [pkg, setPkg] = useState("");
  const [version, setVersion] = useState("");
  const [pool, setPool] = useState("all");
  const [includeDriver, setIncludeDriver] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<{ step: number; total: number } | null>(null);
  const [result, setResult] = useState<InstallLibraryResult | null>(null);
  const [installLogs, setInstallLogs] = useState<LogRow[]>([]);
  const installIdRef = useRef<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!lastEvent || (lastEvent as { source?: string }).source !== "libraries") return;
    const row = lastEvent as unknown as LogRow;
    const meta = row.metadata ?? {};
    if (installIdRef.current && meta.install_id !== installIdRef.current) return;
    setInstallLogs((prev) => {
      if (prev.some((l) => l.id === row.id)) return prev;
      return [...prev.slice(-99), row];
    });
    if (meta?.step && meta?.total) {
      setProgress({ step: Number(meta.step), total: Number(meta.total) });
    }
  }, [lastEvent]);

  useEffect(() => {
    if (installing && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [installLogs, installing]);

  async function install(e: React.FormEvent) {
    e.preventDefault();
    if (!pkg.trim()) return;
    setInstalling(true);
    setResult(null);
    setInstallLogs([]);
    setProgress(null);
    installIdRef.current = null;
    try {
      const res = await api.installLibrary(
        pkg.trim(),
        version.trim() || "latest",
        pool,
        includeDriver,
      );
      installIdRef.current = res.install_id;
      setResult(res);
      if (res.total_targets && res.results) {
        setProgress({ step: res.results.length, total: res.total_targets });
      }
      reload();
      refresh();
    } catch (err) {
      setResult({
        ok: false,
        install_id: "",
        package: pkg,
        version: version || "latest",
        message: err instanceof Error ? err.message : "Install failed",
        results: [],
      });
    } finally {
      setInstalling(false);
    }
  }

  const pct = progress && progress.total > 0
    ? Math.round((progress.step / progress.total) * 100)
    : installing ? 5 : 0;

  return (
    <>
      <Header
        title="Libraries"
        subtitle="Install Python packages on agents and the driver via pip"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reload(); }}
      />
      <div className="flex-1 space-y-6 p-6">
        <form onSubmit={install} className="card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Plus className="h-4 w-4" />
            Install Package
          </h2>
          <p className="mt-2 text-xs text-slate-500">
            PySpark is large (~300MB) and needs Java 11+ on each worker. Install Java first, then pyspark.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Package</label>
              <input
                value={pkg}
                onChange={(e) => setPkg(e.target.value)}
                placeholder="numpy"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-mesh-500 focus:ring-2 focus:ring-mesh-500/20"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Version</label>
              <input
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="latest"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-mesh-500 focus:ring-2 focus:ring-mesh-500/20"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Pool</label>
              <select
                value={pool}
                onChange={(e) => setPool(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-mesh-500"
              >
                <option value="all">All nodes</option>
                <option value="cpu">CPU pool</option>
                <option value="gpu">GPU pool</option>
                <option value="night">Night pool</option>
              </select>
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={includeDriver}
                onChange={(e) => setIncludeDriver(e.target.checked)}
                className="rounded border-slate-300"
              />
              Include driver host
            </label>
            <button type="submit" disabled={installing || !pkg.trim()} className="btn-primary">
              <Package className="h-4 w-4" />
              {installing ? "Installing…" : "Install"}
            </button>
          </div>

          {(installing || result) && (
            <div className="mt-5 space-y-3 border-t border-slate-100 pt-4">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  {installing
                    ? `Installing ${pkg}${version ? `==${version}` : ""}…`
                    : result?.message}
                </span>
                <span>{pct}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    result && !result.ok ? "bg-amber-500" : "bg-mesh-500",
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}
        </form>

        {result && result.results.length > 0 && (
          <div className="card overflow-hidden">
            <div className="border-b border-slate-200 px-5 py-3">
              <h2 className="text-sm font-semibold text-slate-900">Install Results</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-head">Target</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">Message</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r) => (
                  <tr key={`${r.target}-${r.hostname}`} className="hover:bg-slate-50/50">
                    <td className="table-cell font-medium">
                      {r.hostname}
                      <span className="ml-1 text-xs text-slate-400">({r.target})</span>
                    </td>
                    <td className="table-cell">
                      {r.ok ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600">
                          <CheckCircle2 className="h-4 w-4" /> Success
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-600">
                          <XCircle className="h-4 w-4" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="table-cell max-w-md font-mono text-xs text-slate-600">
                      <details className="cursor-pointer">
                        <summary className="truncate" title={r.message}>
                          {r.ok ? r.message : r.message.split("\n")[0]}
                        </summary>
                        {(r.log || r.message) && (
                          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-100 p-2 text-[11px] text-slate-700">
                            {r.log || r.message}
                          </pre>
                        )}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {(installing || installLogs.length > 0) && (
          <div className="card overflow-hidden">
            <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-3">
              <Terminal className="h-4 w-4 text-slate-500" />
              <h2 className="text-sm font-semibold text-slate-900">Install Log</h2>
            </div>
            <div className="max-h-64 overflow-y-auto bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-300">
              {installLogs.map((log) => (
                <div key={log.id} className="whitespace-pre-wrap break-all">
                  <span className={cn("mr-2", logLevelColor(log.level))}>[{log.level}]</span>
                  {log.message}
                </div>
              ))}
              {installing && installLogs.length === 0 && (
                <div className="text-slate-500">Waiting for install output…</div>
              )}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        <div className="card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Installed Libraries</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-head">Package</th>
                <th className="table-head">Version</th>
                <th className="table-head">Pool</th>
                <th className="table-head">Nodes</th>
              </tr>
            </thead>
            <tbody>
              {(libraries ?? []).map((lib) => (
                <tr key={lib.name} className="hover:bg-slate-50/50">
                  <td className="table-cell font-medium text-slate-900">{lib.name}</td>
                  <td className="table-cell font-mono text-sm">{lib.version || "—"}</td>
                  <td className="table-cell capitalize">{lib.pool}</td>
                  <td className="table-cell tabular-nums">{lib.nodes}</td>
                </tr>
              ))}
              {!libraries?.length && (
                <tr>
                  <td colSpan={4} className="table-cell py-10 text-center text-slate-400">
                    No packages reported — agents scan pip packages at registration
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
