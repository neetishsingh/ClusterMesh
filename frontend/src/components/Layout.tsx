import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useClusterStream } from "@/api/useStream";
import { createContext, useContext } from "react";
import { ClusterStatus } from "@/api/client";

interface AppShellContext {
  cluster: ClusterStatus | null;
  connected: boolean;
  refresh: () => void;
  lastEvent: Record<string, unknown> | null;
}

const ShellContext = createContext<AppShellContext>({
  cluster: null,
  connected: false,
  refresh: () => {},
  lastEvent: null,
});

export function useShell() {
  return useContext(ShellContext);
}

export function Layout() {
  const { cluster, connected, refresh, lastEvent } = useClusterStream();

  return (
    <ShellContext.Provider value={{ cluster, connected, refresh, lastEvent }}>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </ShellContext.Provider>
  );
}
