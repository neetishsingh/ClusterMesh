import { Header } from "@/components/Header";
import { Badge } from "@/components/Badge";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { Globe, Radio, RefreshCw, Plus } from "lucide-react";
import { useState } from "react";

export function MeshPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: mesh, reload } = usePolling(() => api.mesh(), 8000);
  const { data: sites } = usePolling(() => api.sites(), 10000);
  const [probing, setProbing] = useState(false);

  async function probe() {
    setProbing(true);
    try {
      await api.probeMesh();
      reload();
      refresh();
    } finally {
      setProbing(false);
    }
  }

  return (
    <>
      <Header
        title="Mesh VPN"
        subtitle="Multi-site overlay — cross-region agent connectivity"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reload(); }}
        actions={
          <button type="button" onClick={probe} disabled={probing} className="btn-primary !py-1.5 !text-xs">
            <RefreshCw className={probing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            Probe Peers
          </button>
        }
      />
      <div className="flex-1 space-y-6 p-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-mesh-50 p-2.5 text-mesh-600">
                <Globe className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Local Site</p>
                <p className="text-lg font-semibold text-slate-900">
                  {mesh?.site_id ?? cluster?.site_id ?? "default"}
                </p>
              </div>
            </div>
          </div>
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-emerald-50 p-2.5 text-emerald-600">
                <Radio className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Relay</p>
                <p className="text-lg font-semibold text-slate-900">
                  {mesh?.relay ? "Active" : "Not configured"}
                </p>
                {mesh?.relay && (
                  <p className="mt-1 font-mono text-xs text-slate-500">
                    {mesh.relay.public || mesh.relay.listen}
                  </p>
                )}
              </div>
            </div>
          </div>
          <div className="card p-5">
            <p className="text-sm font-medium text-slate-500">Remote Peers</p>
            <p className="mt-1 text-3xl font-semibold text-slate-900">{mesh?.peers?.length ?? 0}</p>
            <p className="mt-1 text-xs text-slate-400">
              {mesh?.relay?.connections ?? 0} relay connections
            </p>
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Remote Sites</h2>
            <span className="text-xs text-slate-400">{mesh?.peers?.length ?? 0} peers</span>
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-head">Site</th>
                <th className="table-head">Region</th>
                <th className="table-head">Relay</th>
                <th className="table-head">gRPC</th>
                <th className="table-head">Latency</th>
                <th className="table-head">Status</th>
              </tr>
            </thead>
            <tbody>
              {(mesh?.peers ?? []).map((p) => (
                <tr key={p.site_id} className="hover:bg-slate-50/50">
                  <td className="table-cell font-medium text-slate-900">{p.site_id}</td>
                  <td className="table-cell text-slate-500">{p.region}</td>
                  <td className="table-cell font-mono text-xs">{p.relay_address}</td>
                  <td className="table-cell font-mono text-xs">{p.grpc_address}</td>
                  <td className="table-cell tabular-nums">
                    {p.latency_ms >= 0 ? `${p.latency_ms.toFixed(0)} ms` : "—"}
                  </td>
                  <td className="table-cell">
                    <Badge label={p.status === "reachable" ? "HEALTHY" : "SUSPECTED"} />
                  </td>
                </tr>
              ))}
              {!mesh?.peers?.length && (
                <tr>
                  <td colSpan={6} className="table-cell py-10 text-center text-slate-400">
                    No remote peers — add via <code className="rounded bg-slate-100 px-1">--mesh-config sites.yaml</code>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card overflow-hidden">
          <div className="border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Connected Compute Sites</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-head">Site</th>
                <th className="table-head">Nodes</th>
                <th className="table-head">Healthy</th>
              </tr>
            </thead>
            <tbody>
              {(sites ?? []).map((s) => (
                <tr key={s.site} className="hover:bg-slate-50/50">
                  <td className="table-cell font-medium">{s.site}</td>
                  <td className="table-cell tabular-nums">{s.nodes}</td>
                  <td className="table-cell tabular-nums">{s.healthy}</td>
                </tr>
              ))}
              {!sites?.length && (
                <tr>
                  <td colSpan={3} className="table-cell py-8 text-center text-slate-400">
                    No nodes registered yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Plus className="h-4 w-4" />
            Quick Start
          </h2>
          <div className="mt-3 space-y-2 font-mono text-xs text-slate-600">
            <div className="rounded-lg bg-slate-50 p-3">
              mesh-platform --mesh-config config/sites.example.yaml --site bangalore
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              mesh-agent --driver relay-host:6000 --location london
            </div>
            <div className="rounded-lg bg-slate-50 p-3">mesh-soak --hours 24 --nodes 50</div>
          </div>
        </div>
      </div>
    </>
  );
}
