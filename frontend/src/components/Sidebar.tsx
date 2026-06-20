import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Server,
  Briefcase,
  ScrollText,
  Package,
  Network,
  Globe,
  HardDrive,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/notebook", label: "Notebook", icon: BookOpen },
  { to: "/nodes", label: "Compute", icon: Server },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/libraries", label: "Libraries", icon: Package },
  { to: "/cluster", label: "Cluster", icon: Network },
  { to: "/mesh", label: "Mesh VPN", icon: Globe },
  { to: "/memory", label: "Memory", icon: HardDrive },
];

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-14 items-center gap-2.5 border-b border-slate-200 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-mesh-600">
          <Network className="h-4 w-4 text-white" />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-900">ComputeMesh</div>
          <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
            Enterprise Compute
          </div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 p-3">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                isActive
                  ? "bg-mesh-50 text-mesh-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-200 p-4">
        <p className="text-xs text-slate-400">v0.8.0 · Phase 8</p>
      </div>
    </aside>
  );
}
