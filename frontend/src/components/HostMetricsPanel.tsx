import { NodeRow } from "@/api/client";
import { ProgressBar } from "@/components/ProgressBar";
import { cn } from "@/lib/utils";

interface HostMetricsPanelProps {
  node: NodeRow;
  className?: string;
}

function fmt(v: number | null | undefined, suffix = "") {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v}${suffix}`;
}

export function HostMetricsPanel({ node, className }: HostMetricsPanelProps) {
  const hm = node.host_metrics;
  const mem = hm?.memory;
  const procs = node.top_processes ?? hm?.processes?.top ?? [];

  return (
    <div className={cn("grid gap-4 bg-slate-50/80 p-4 lg:grid-cols-3", className)}>
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">CPU</h3>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {node.cpu_brand || "Processor"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          {node.cpu_physical ?? "—"} physical · {node.cpu_total} logical cores
        </p>
        <div className="mt-3 space-y-2">
          <div>
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>Total utilization</span>
              <span>{fmt(node.cpu_utilization, "%")}</span>
            </div>
            <ProgressBar value={node.cpu_utilization ?? 0} showLabel={false} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded bg-blue-50 px-2 py-1.5">
              <div className="font-semibold text-blue-700">{fmt(node.cpu_user_pct, "%")}</div>
              <div className="text-blue-600/80">User</div>
            </div>
            <div className="rounded bg-amber-50 px-2 py-1.5">
              <div className="font-semibold text-amber-700">{fmt(node.cpu_system_pct, "%")}</div>
              <div className="text-amber-600/80">System</div>
            </div>
            <div className="rounded bg-emerald-50 px-2 py-1.5">
              <div className="font-semibold text-emerald-700">{fmt(node.cpu_idle_pct, "%")}</div>
              <div className="text-emerald-600/80">Idle</div>
            </div>
          </div>
          {node.load_avg && (
            <p className="text-xs text-slate-500">
              Load avg: {node.load_avg.map((v) => v.toFixed(2)).join(" · ")}
            </p>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Memory</h3>
        <p className="mt-2 text-sm text-slate-700">
          {fmt(node.memory_used_gb ?? (node.ram_gb_total - node.ram_gb_free), " GB")} used of{" "}
          {fmt(node.ram_gb_total, " GB")}
        </p>
        <div className="mt-3 space-y-2 text-xs text-slate-600">
          {mem?.wired_gb != null && (
            <div className="flex justify-between"><span>Wired</span><span>{mem.wired_gb} GB</span></div>
          )}
          {mem?.compressed_gb != null && (
            <div className="flex justify-between"><span>Compressed</span><span>{mem.compressed_gb} GB</span></div>
          )}
          {mem?.app_gb != null && (
            <div className="flex justify-between"><span>App memory</span><span>{mem.app_gb} GB</span></div>
          )}
          <div className="flex justify-between"><span>Available</span><span>{node.ram_gb_free} GB</span></div>
          {(node.memory_swap_gb ?? mem?.swap_gb) != null && (
            <div className="flex justify-between"><span>Swap used</span><span>{node.memory_swap_gb ?? mem?.swap_gb} GB</span></div>
          )}
        </div>
        <div className="mt-3">
          <ProgressBar
            value={node.ram_gb_total ? ((node.ram_gb_total - node.ram_gb_free) / node.ram_gb_total) * 100 : 0}
            showLabel={false}
          />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Processes</h3>
        <p className="mt-2 text-sm text-slate-700">
          {node.process_count ?? procs.length ?? "—"} processes · {node.thread_count ?? "—"} threads
        </p>
        {node.gpu_name && (
          <p className="mt-1 text-xs text-slate-500">GPU: {node.gpu_name}</p>
        )}
        {node.user_active != null && (
          <p className="mt-1 text-xs text-slate-500">
            User {node.user_active ? "active" : "idle"}
          </p>
        )}
        <div className="mt-3 overflow-hidden rounded border border-slate-100">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-2 py-1 text-left font-medium">Process</th>
                <th className="px-2 py-1 text-right font-medium">CPU</th>
                <th className="px-2 py-1 text-right font-medium">Threads</th>
                <th className="px-2 py-1 text-right font-medium">Mem</th>
              </tr>
            </thead>
            <tbody>
              {procs.slice(0, 8).map((p) => (
                <tr key={p.pid} className="border-t border-slate-100">
                  <td className="max-w-[120px] truncate px-2 py-1 font-medium text-slate-800" title={p.name}>
                    {p.name}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">{p.cpu_pct}%</td>
                  <td className="px-2 py-1 text-right tabular-nums">{p.threads}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{p.memory_mb}M</td>
                </tr>
              ))}
              {!procs.length && (
                <tr>
                  <td colSpan={4} className="px-2 py-3 text-center text-slate-400">
                    Process list loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] text-slate-400">
          CPU % is per-core (Activity Monitor style — can exceed 100% on multi-core).
        </p>
      </section>
    </div>
  );
}
