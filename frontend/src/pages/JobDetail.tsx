import { useParams, Link } from "react-router-dom";
import { Header } from "@/components/Header";
import { Badge } from "@/components/Badge";
import { ProgressBar } from "@/components/ProgressBar";
import { useShell } from "@/components/Layout";
import { usePolling } from "@/api/useStream";
import { api } from "@/api/client";
import { ArrowLeft } from "lucide-react";

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { cluster, connected, refresh } = useShell();
  const { data: job, reload } = usePolling(
    () => (jobId ? api.job(jobId) : Promise.reject("no id")),
    3000,
  );

  const tasks = job && "tasks" in job ? job.tasks : [];

  return (
    <>
      <Header
        title={job && "name" in job ? job.name || "Job Detail" : "Job Detail"}
        subtitle={jobId}
        cluster={cluster}
        connected={connected}
        onRefresh={() => { refresh(); reload(); }}
        actions={
          <Link to="/jobs" className="btn-secondary !py-1.5 !text-xs">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Link>
        }
      />
      <div className="flex-1 space-y-6 p-6">
        {job && "state" in job && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <Badge label={job.state} />
              <span className="text-sm text-slate-500">{tasks.length} tasks</span>
              {job.error && (
                <span className="rounded-lg bg-red-50 px-3 py-1 text-sm text-red-700">{job.error}</span>
              )}
            </div>

            <div className="card overflow-hidden">
              <div className="border-b border-slate-200 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900">Task DAG</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px]">
                  <thead>
                    <tr>
                      <th className="table-head">Task</th>
                      <th className="table-head">State</th>
                      <th className="table-head">Progress</th>
                      <th className="table-head">Node</th>
                      <th className="table-head">Checkpoint</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((t) => (
                      <tr key={t.task_id} className="hover:bg-slate-50/50">
                        <td className="table-cell">
                          <div className="font-medium text-slate-900">{t.name}</div>
                          <div className="font-mono text-xs text-slate-400">{t.task_id.slice(0, 14)}…</div>
                        </td>
                        <td className="table-cell"><Badge label={t.state} /></td>
                        <td className="table-cell">
                          <div className="w-36"><ProgressBar value={t.progress} /></div>
                        </td>
                        <td className="table-cell font-mono text-xs text-slate-600">
                          {t.assigned_node?.slice(0, 12) ?? "—"}
                        </td>
                        <td className="table-cell text-xs text-slate-500">
                          {t.checkpoint ? "✓ saved" : "—"}
                        </td>
                      </tr>
                    ))}
                    {!tasks.length && (
                      <tr>
                        <td colSpan={5} className="table-cell py-8 text-center text-slate-400">
                          No tasks yet
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
