import { Link } from "react-router-dom";
import { Header } from "@/components/Header";
import { Badge } from "@/components/Badge";
import { ProgressBar } from "@/components/ProgressBar";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { Trash2 } from "lucide-react";
import { useState } from "react";

export function JobsPage() {
  const { cluster, connected, refresh } = useShell();
  const { data: jobs, reload } = usePolling(() => api.jobs(), 4000);
  const [cancelling, setCancelling] = useState<string | null>(null);

  async function cancel(jobId: string) {
    setCancelling(jobId);
    try {
      await api.cancelJob(jobId);
      reload();
    } finally {
      setCancelling(null);
    }
  }

  return (
    <>
      <Header
        title="Jobs"
        subtitle="Monitor workloads, task progress, and failures"
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reload(); }}
      />
      <div className="flex-1 p-6">
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px]">
              <thead>
                <tr>
                  <th className="table-head">Job</th>
                  <th className="table-head">State</th>
                  <th className="table-head">Tasks</th>
                  <th className="table-head">Progress</th>
                  <th className="table-head">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(jobs ?? []).map((job) => {
                  const avgProgress =
                    job.tasks.length > 0
                      ? job.tasks.reduce((s, t) => s + t.progress, 0) / job.tasks.length
                      : 0;
                  const running = job.tasks.filter((t) => t.state === "RUNNING").length;
                  return (
                    <tr key={job.job_id} className="hover:bg-slate-50/50">
                      <td className="table-cell">
                        <Link
                          to={`/jobs/${job.job_id}`}
                          className="font-medium text-mesh-600 hover:text-mesh-700 hover:underline"
                        >
                          {job.name || job.job_id.slice(0, 12)}
                        </Link>
                        <div className="font-mono text-xs text-slate-400">{job.job_id.slice(0, 16)}…</div>
                        {job.error && (
                          <div className="mt-1 text-xs text-red-600">{job.error}</div>
                        )}
                      </td>
                      <td className="table-cell"><Badge label={job.state} /></td>
                      <td className="table-cell tabular-nums">
                        {running}/{job.task_count} running
                      </td>
                      <td className="table-cell">
                        <div className="w-32"><ProgressBar value={avgProgress} /></div>
                      </td>
                      <td className="table-cell">
                        <div className="flex gap-2">
                          <Link to={`/jobs/${job.job_id}`} className="btn-secondary !px-2 !py-1 !text-xs">
                            Details
                          </Link>
                          <button
                            type="button"
                            disabled={cancelling === job.job_id}
                            onClick={() => cancel(job.job_id)}
                            className="btn-danger"
                          >
                            <Trash2 className="h-3 w-3" />
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!jobs?.length && (
                  <tr>
                    <td colSpan={5} className="table-cell py-12 text-center text-slate-400">
                      No active jobs — submit work with the ComputeMesh SDK
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
