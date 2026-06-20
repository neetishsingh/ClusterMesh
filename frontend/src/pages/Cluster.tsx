import { useState } from "react";
import { Header } from "@/components/Header";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { RefreshCw, Shield, Database, Radio, UserPlus } from "lucide-react";

export function ClusterPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: joinInfo } = usePolling(() => api.joinInfo(), 60000);
  const [rebalancing, setRebalancing] = useState(false);
  const [lastMigration, setLastMigration] = useState<number | null>(null);

  async function rebalance() {
    setRebalancing(true);
    try {
      const res = await api.rebalance();
      setLastMigration(res.migrations);
      refresh();
    } finally {
      setRebalancing(false);
    }
  }

  return (
    <>
      <Header
        title="Cluster"
        subtitle="HA driver, join instructions, scheduler"
        cluster={cluster}
        connected={connected}
        onRefresh={refresh}
        actions={
          <button type="button" onClick={rebalance} disabled={rebalancing} className="btn-primary !py-1.5 !text-xs">
            <RefreshCw className={rebalancing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            Rebalance
          </button>
        }
      />
      <div className="flex-1 space-y-6 p-6">
        <div className="card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <UserPlus className="h-4 w-4 text-mesh-600" />
            Join another machine to this mesh
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            On any machine with Python 3.11+, install from pip and join — no git clone required.
          </p>
          <div className="mt-4 space-y-3">
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">1. Install & join (one command)</p>
              <div className="rounded-lg bg-slate-900 p-3 font-mono text-xs text-emerald-400">
                pip install clustermesh<br />
                clustermesh join &lt;DRIVER_IP&gt;:{joinInfo?.driver_grpc ?? "50050"} --open
              </div>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">Local worker UI</p>
              <div className="rounded-lg bg-slate-900 p-3 font-mono text-xs text-emerald-400">
                http://127.0.0.1:50052 — CPU, memory, processes on this machine
              </div>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">Same LAN (auto-discovery)</p>
              <div className="rounded-lg bg-slate-900 p-3 font-mono text-xs text-emerald-400">
                clustermesh join --discover --open
              </div>
            </div>
            <p className="text-xs text-slate-500">
              Ports: driver {joinInfo?.driver_grpc ?? "50050"}, agent {joinInfo?.agent_grpc ?? "50051"},
              worker UI 50052, dashboard {joinInfo?.dashboard_port ?? 8080}.
              Full guide: <code>docs/join-mesh.md</code>
            </p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-mesh-50 p-2.5 text-mesh-600"><Shield className="h-5 w-5" /></div>
              <div>
                <p className="text-sm font-medium text-slate-500">Driver Role</p>
                <p className="text-lg font-semibold">{cluster?.is_leader ? "Leader" : "Follower"}</p>
              </div>
            </div>
          </div>
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-emerald-50 p-2.5 text-emerald-600"><Database className="h-5 w-5" /></div>
              <div>
                <p className="text-sm font-medium text-slate-500">Workers</p>
                <p className="text-lg font-semibold">{cluster?.healthy_nodes ?? 0} healthy</p>
              </div>
            </div>
          </div>
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-amber-50 p-2.5 text-amber-600"><Radio className="h-5 w-5" /></div>
              <div>
                <p className="text-sm font-medium text-slate-500">Live stream</p>
                <p className="text-lg font-semibold">{connected ? "Connected" : "Polling"}</p>
              </div>
            </div>
          </div>
        </div>

        {lastMigration !== null && (
          <p className="text-sm text-slate-600">Last rebalance migrated <strong>{lastMigration}</strong> tasks.</p>
        )}
      </div>
    </>
  );
}
