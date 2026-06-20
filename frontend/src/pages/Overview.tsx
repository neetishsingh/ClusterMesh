import { Header } from "@/components/Header";
import { StatCard } from "@/components/StatCard";
import { ProgressBar } from "@/components/ProgressBar";
import { Badge } from "@/components/Badge";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { Cpu, HardDrive, Activity, Server, Zap } from "lucide-react";

export function OverviewPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: nodes } = usePolling(() => api.nodes(), 5000);

  const utilizedCores =
    cluster ? cluster.total_cpu_cores - cluster.free_cpu_cores : 0;
  const utilPct =
    cluster?.cpu_utilization_pct ??
    (cluster && cluster.total_cpu_cores
      ? (utilizedCores / cluster.total_cpu_cores) * 100
      : 0);
  const hasNodes = (cluster?.total_nodes ?? 0) > 0;
  const utilSubtitle = hasNodes
    ? cluster!.driver_host_included
      ? `${utilPct.toFixed(0)}% avg across agents + driver host`
      : `${utilPct.toFixed(0)}% avg across ${cluster!.total_nodes} agent${cluster!.total_nodes !== 1 ? "s" : ""}`
    : cluster?.driver_host_included
      ? `${utilPct.toFixed(0)}% on driver host`
      : "—";

  return (
    <>
      <Header
        title="Overview"
        subtitle={hasNodes ? "Live cluster metrics from registered agents" : "Start mesh-agent on a machine to see real data"}
        cluster={cluster}
        connected={connected}
        onRefresh={refresh}
      />
      <div className="flex-1 space-y-6 p-6">
        {!hasNodes && (
          <div className="card border-dashed border-amber-300 bg-amber-50/50 p-6 text-center">
            <p className="font-medium text-amber-900">No workers connected</p>
            <p className="mt-1 text-sm text-amber-700">
              Run <code className="rounded bg-amber-100 px-1">mesh-agent --driver YOUR_IP:50050</code> on any machine.
              See the <strong>Cluster</strong> page for join instructions.
            </p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            title="Healthy Nodes"
            value={hasNodes ? cluster!.healthy_nodes : "—"}
            subtitle={hasNodes ? `${cluster!.total_nodes} registered` : "Waiting for agents"}
            icon={Server}
            accent="blue"
          />
          <StatCard
            title="CPU Utilization"
            value={hasNodes || cluster?.driver_host_included ? `${utilPct.toFixed(0)}%` : "—"}
            subtitle={utilSubtitle}
            icon={Cpu}
            accent="green"
          />
          <StatCard
            title="Active Tasks"
            value={hasNodes ? cluster!.active_tasks : "—"}
            subtitle={hasNodes ? `${cluster!.active_jobs} jobs` : "—"}
            icon={Activity}
            accent="amber"
          />
          <StatCard
            title="Free Memory"
            value={hasNodes ? `${cluster!.free_ram_gb.toFixed(0)} GB` : "—"}
            subtitle={hasNodes ? `of ${cluster!.total_ram_gb.toFixed(0)} GB cluster RAM` : "—"}
            icon={HardDrive}
            accent="blue"
          />
        </div>

        {hasNodes && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card p-5">
              <h2 className="text-sm font-semibold text-slate-900">Resource Utilization</h2>
              <div className="mt-5 space-y-5">
                <div>
                  <div className="mb-1.5 flex justify-between text-xs text-slate-500">
                    <span>CPU (cluster avg)</span>
                    <span>{utilPct.toFixed(0)}%</span>
                  </div>
                  <ProgressBar value={utilPct} showLabel={false} />
                </div>
                <div>
                  <div className="mb-1.5 flex justify-between text-xs text-slate-500">
                    <span>Memory</span>
                    <span>
                      {(cluster!.total_ram_gb - cluster!.free_ram_gb).toFixed(0)} / {cluster!.total_ram_gb.toFixed(0)} GB
                    </span>
                  </div>
                  <ProgressBar
                    value={
                      cluster!.total_ram_gb
                        ? ((cluster!.total_ram_gb - cluster!.free_ram_gb) / cluster!.total_ram_gb) * 100
                        : 0
                    }
                    showLabel={false}
                  />
                </div>
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  <Zap className="h-4 w-4 text-amber-500" />
                  <span>{cluster!.total_gpus} GPUs · site {cluster!.site_id ?? "default"}</span>
                </div>
              </div>
            </div>

            <div className="card p-5">
              <h2 className="text-sm font-semibold text-slate-900">Node Health</h2>
              <div className="mt-4 grid grid-cols-3 gap-3">
                {[
                  { label: "Healthy", count: cluster!.healthy_nodes, color: "text-emerald-600 bg-emerald-50" },
                  { label: "Suspected", count: cluster!.suspected_nodes, color: "text-amber-600 bg-amber-50" },
                  { label: "Dead", count: cluster!.dead_nodes, color: "text-red-600 bg-red-50" },
                ].map((item) => (
                  <div key={item.label} className={`rounded-lg p-4 text-center ${item.color}`}>
                    <div className="text-2xl font-bold">{item.count}</div>
                    <div className="mt-1 text-xs font-medium">{item.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Compute Nodes</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr>
                  <th className="table-head">Hostname</th>
                  <th className="table-head">State</th>
                  <th className="table-head">Site</th>
                  <th className="table-head">CPU</th>
                  <th className="table-head">RAM</th>
                </tr>
              </thead>
              <tbody>
                {(nodes ?? []).map((n) => (
                  <tr key={n.node_id} className="hover:bg-slate-50/50">
                    <td className="table-cell font-medium text-slate-900">{n.hostname}</td>
                    <td className="table-cell"><Badge label={n.state} /></td>
                    <td className="table-cell text-slate-500">{n.location}</td>
                    <td className="table-cell">
                      <div className="w-24"><ProgressBar value={n.cpu_utilization} /></div>
                      <span className="text-xs text-slate-400">
                        {n.cpu_physical ?? "?"}/{n.cpu_total} cores
                      </span>
                    </td>
                    <td className="table-cell tabular-nums">
                      {(n.memory_used_gb ?? (n.ram_gb_total - n.ram_gb_free)).toFixed(1)}/{n.ram_gb_total} GB
                    </td>
                  </tr>
                ))}
                {!nodes?.length && (
                  <tr>
                    <td colSpan={5} className="table-cell py-8 text-center text-slate-400">
                      No nodes — connect workers with mesh-agent
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
