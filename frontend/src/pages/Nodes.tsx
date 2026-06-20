import { Fragment, useState } from "react";
import { Header } from "@/components/Header";
import { Badge } from "@/components/Badge";
import { ProgressBar } from "@/components/ProgressBar";
import { HostMetricsPanel } from "@/components/HostMetricsPanel";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api, NodeRow } from "@/api/client";
import { Pause, Droplets, Search, ChevronDown, ChevronRight } from "lucide-react";

export function NodesPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: nodes, reload } = usePolling(() => api.nodes(), 4000);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const filtered = (nodes ?? []).filter(
    (n) =>
      !filter ||
      n.hostname.toLowerCase().includes(filter.toLowerCase()) ||
      n.node_id.toLowerCase().includes(filter.toLowerCase()),
  );

  async function nodeAction(node: NodeRow, action: "pause" | "drain") {
    setActionLoading(`${action}-${node.node_id}`);
    try {
      if (action === "pause") await api.pauseNode(node.node_id);
      else await api.drainNode(node.node_id);
      reload();
      refresh();
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <>
      <Header
        title="Compute"
        subtitle="Activity Monitor-style host metrics from each mesh-agent"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reload(); }}
      />
      <div className="flex-1 p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              placeholder="Search nodes..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-mesh-500 focus:ring-2 focus:ring-mesh-500/20"
            />
          </div>
          <span className="text-sm text-slate-500">{filtered.length} nodes</span>
        </div>

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr>
                  <th className="table-head w-8" />
                  <th className="table-head">Node</th>
                  <th className="table-head">State</th>
                  <th className="table-head">Pool</th>
                  <th className="table-head">CPU</th>
                  <th className="table-head">Memory</th>
                  <th className="table-head">Processes</th>
                  <th className="table-head">Battery</th>
                  <th className="table-head">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((n) => {
                  const open = expanded === n.node_id;
                  return (
                    <Fragment key={n.node_id}>
                      <tr key={n.node_id} className="hover:bg-slate-50/50">
                        <td className="table-cell">
                          <button
                            type="button"
                            onClick={() => setExpanded(open ? null : n.node_id)}
                            className="text-slate-400 hover:text-slate-600"
                          >
                            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </button>
                        </td>
                        <td className="table-cell">
                          <div className="font-medium text-slate-900">{n.hostname}</div>
                          <div className="text-xs text-slate-500">{n.os || n.location}</div>
                          {n.cpu_brand && (
                            <div className="mt-0.5 text-[11px] text-slate-400">{n.cpu_brand}</div>
                          )}
                          {n.preemptible && (
                            <span className="mt-1 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                              Preemptible
                            </span>
                          )}
                        </td>
                        <td className="table-cell"><Badge label={n.state} /></td>
                        <td className="table-cell capitalize">{n.pool.toLowerCase()}</td>
                        <td className="table-cell">
                          <div className="w-28"><ProgressBar value={n.cpu_utilization} /></div>
                          <span className="text-xs text-slate-400">
                            {n.cpu_physical ?? "?"}/{n.cpu_total} cores · U{n.cpu_user_pct ?? 0} S{n.cpu_system_pct ?? 0}
                          </span>
                        </td>
                        <td className="table-cell tabular-nums text-sm">
                          {(n.memory_used_gb ?? (n.ram_gb_total - n.ram_gb_free)).toFixed(1)}/{n.ram_gb_total} GB
                          {n.memory_wired_gb != null && (
                            <div className="text-xs text-slate-400">wired {n.memory_wired_gb} GB</div>
                          )}
                        </td>
                        <td className="table-cell tabular-nums text-sm">
                          {n.process_count ?? "—"}
                          <div className="text-xs text-slate-400">{n.thread_count ?? "—"} threads</div>
                        </td>
                        <td className="table-cell">
                          {n.battery_pct != null ? `${n.battery_pct}%` : "—"}
                        </td>
                        <td className="table-cell">
                          <div className="flex gap-1">
                            <button
                              type="button"
                              disabled={!!actionLoading}
                              onClick={() => nodeAction(n, "pause")}
                              className="btn-secondary !px-2 !py-1 !text-xs"
                              title="Pause scheduling"
                            >
                              <Pause className="h-3 w-3" />
                            </button>
                            <button
                              type="button"
                              disabled={!!actionLoading}
                              onClick={() => nodeAction(n, "drain")}
                              className="btn-secondary !px-2 !py-1 !text-xs"
                              title="Drain tasks"
                            >
                              <Droplets className="h-3 w-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {open && (
                        <tr key={`${n.node_id}-detail`}>
                          <td colSpan={9} className="p-0">
                            <HostMetricsPanel node={n} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {!filtered.length && (
                  <tr>
                    <td colSpan={9} className="table-cell py-12 text-center text-slate-400">
                      {nodes?.length ? "No nodes match your search" : "Waiting for agents to register…"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
