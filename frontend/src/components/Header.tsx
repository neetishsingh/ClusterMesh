import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { ClusterStatus } from "@/api/client";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
  cluster: ClusterStatus | null;
  connected: boolean;
  onRefresh?: () => void;
  actions?: React.ReactNode;
}

export function Header({ title, subtitle, cluster, connected, onRefresh, actions }: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-6">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-3">
          {cluster && (
            <div className="hidden items-center gap-4 text-xs text-slate-500 md:flex">
              <span>
                <strong className="text-slate-700">{cluster.healthy_nodes}</strong>/{cluster.total_nodes} nodes
              </span>
              <span>
                <strong className="text-slate-700">{cluster.active_tasks}</strong> tasks
              </span>
              {cluster.is_leader !== undefined && (
                <span className={cn("rounded-full px-2 py-0.5 font-medium", cluster.is_leader ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500")}>
                  {cluster.is_leader ? "Leader" : "Follower"}
                </span>
              )}
            </div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            {connected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-emerald-500" />
                Live
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-amber-500" />
                Polling
              </>
            )}
          </div>
          {onRefresh && (
            <button type="button" onClick={onRefresh} className="btn-secondary !px-2.5 !py-2" title="Refresh">
              <RefreshCw className="h-4 w-4" />
            </button>
          )}
          {actions}
        </div>
      </div>
    </header>
  );
}
