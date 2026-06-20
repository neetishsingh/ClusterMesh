import { Header } from "@/components/Header";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { HardDrive, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ProgressBar } from "@/components/ProgressBar";

export function MemoryPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: pool, reload: reloadPool } = usePolling(() => api.memoryPool(), 5000);
  const { data: allocations, reload: reloadAllocs } = usePolling(() => api.memoryAllocations(), 5000);
  const [sizeGb, setSizeGb] = useState("8");
  const [allocating, setAllocating] = useState(false);

  async function allocate(e: React.FormEvent) {
    e.preventDefault();
    setAllocating(true);
    try {
      await api.allocateMemory(parseFloat(sizeGb), "dashboard");
      reloadPool();
      reloadAllocs();
      refresh();
    } finally {
      setAllocating(false);
    }
  }

  async function release(id: string) {
    await api.releaseMemory(id);
    reloadPool();
    reloadAllocs();
  }

  const utilPct = pool ? (pool.allocated_gb / pool.total_gb) * 100 : 0;

  return (
    <>
      <Header
        title="Memory Fabric"
        subtitle="Unified logical RAM pool across all compute nodes"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reloadPool(); reloadAllocs(); }}
      />
      <div className="flex-1 space-y-6 p-6">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Total Pool</p>
            <p className="mt-2 text-3xl font-semibold">{pool?.total_gb ?? "—"} GB</p>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Free</p>
            <p className="mt-2 text-3xl font-semibold text-emerald-600">{pool?.free_gb ?? "—"} GB</p>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Allocated</p>
            <p className="mt-2 text-3xl font-semibold text-mesh-600">{pool?.allocated_gb ?? "—"} GB</p>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Nodes</p>
            <p className="mt-2 text-3xl font-semibold">{pool?.node_count ?? "—"}</p>
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-900">Pool Utilization</h2>
          <div className="mt-4">
            <ProgressBar value={utilPct} />
          </div>
        </div>

        <form onSubmit={allocate} className="card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Plus className="h-4 w-4" />
            Allocate Logical Memory
          </h2>
          <div className="mt-4 flex items-end gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Size (GB)</label>
              <input
                type="number"
                min="1"
                step="1"
                value={sizeGb}
                onChange={(e) => setSizeGb(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-mesh-500"
              />
            </div>
            <button type="submit" disabled={allocating} className="btn-primary">
              <HardDrive className="h-4 w-4" />
              {allocating ? "Allocating…" : "Allocate"}
            </button>
          </div>
        </form>

        <div className="card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Active Allocations</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-head">ID</th>
                <th className="table-head">Size</th>
                <th className="table-head">Owner</th>
                <th className="table-head">Segments</th>
                <th className="table-head">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(allocations ?? []).map((a) => (
                <tr key={a.allocation_id} className="hover:bg-slate-50/50">
                  <td className="table-cell font-mono text-xs">{a.allocation_id.slice(0, 12)}…</td>
                  <td className="table-cell tabular-nums">{a.total_gb} GB</td>
                  <td className="table-cell">{a.owner || "—"}</td>
                  <td className="table-cell">
                    {a.segments.map((s) => (
                      <span key={s.node_id} className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                        {s.hostname}: {s.size_gb}GB
                      </span>
                    ))}
                  </td>
                  <td className="table-cell">
                    <button type="button" onClick={() => release(a.allocation_id)} className="btn-danger">
                      <Trash2 className="h-3 w-3" />
                      Release
                    </button>
                  </td>
                </tr>
              ))}
              {!allocations?.length && (
                <tr>
                  <td colSpan={5} className="table-cell py-10 text-center text-slate-400">
                    No allocations — cluster RAM is available as a unified pool
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
