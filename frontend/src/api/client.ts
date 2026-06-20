const API = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

export interface ClusterStatus {
  total_nodes: number;
  healthy_nodes: number;
  suspected_nodes: number;
  dead_nodes: number;
  total_cpu_cores: number;
  free_cpu_cores: number;
  total_ram_gb: number;
  free_ram_gb: number;
  total_gpus: number;
  active_jobs: number;
  active_tasks: number;
  cpu_utilization_pct?: number;
  driver_host_included?: boolean;
  savings_usd?: number;
  is_leader?: boolean;
  leader?: { driver_id: string; term: number } | null;
  site_id?: string;
}

export interface ProcessRow {
  pid: number;
  name: string;
  cpu_pct: number;
  threads: number;
  memory_mb: number;
}

export interface HostMetrics {
  platform?: string;
  cpu?: {
    logical_cores?: number;
    physical_cores?: number;
    brand?: string;
    utilization_pct?: number;
    user_pct?: number;
    system_pct?: number;
    idle_pct?: number;
    load_avg?: number[];
  };
  memory?: {
    total_gb?: number;
    used_gb?: number;
    available_gb?: number;
    wired_gb?: number;
    compressed_gb?: number;
    app_gb?: number;
    swap_gb?: number;
  };
  processes?: {
    total?: number;
    threads_total?: number;
    top?: ProcessRow[];
  };
  gpu?: { count?: number; name?: string; names?: string[] };
}

export interface NodeRow {
  node_id: string;
  hostname: string;
  state: string;
  cpu_total: number;
  cpu_physical?: number | null;
  cpu_free: number;
  cpu_utilization: number;
  cpu_user_pct?: number | null;
  cpu_system_pct?: number | null;
  cpu_idle_pct?: number | null;
  cpu_brand?: string | null;
  load_avg?: number[] | null;
  ram_gb_total: number;
  ram_gb_free: number;
  memory_used_gb?: number | null;
  memory_wired_gb?: number | null;
  memory_compressed_gb?: number | null;
  memory_swap_gb?: number | null;
  process_count?: number | null;
  thread_count?: number | null;
  top_processes?: ProcessRow[];
  gpu_count: number;
  gpu_name?: string | null;
  battery_pct: number | null;
  preemptible: boolean;
  user_active?: boolean;
  location: string;
  pool: string;
  reliability: number;
  is_remote: boolean;
  os?: string;
  host_metrics?: HostMetrics | null;
}

export interface TaskRow {
  task_id: string;
  name: string;
  state: string;
  progress: number;
  assigned_node: string | null;
  checkpoint?: unknown;
}

export interface JobRow {
  job_id: string;
  name: string;
  state: string;
  task_count: number;
  tasks: TaskRow[];
  error: string | null;
  created: string;
}

export interface LogRow {
  id: string;
  timestamp: string;
  level: string;
  source: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface InstallTargetResult {
  target: string;
  hostname: string;
  ok: boolean;
  message: string;
  log?: string;
}

export interface InstallLibraryResult {
  ok: boolean;
  install_id: string;
  package: string;
  version: string;
  message: string;
  results: InstallTargetResult[];
  total_targets?: number;
}

export interface LibraryRow {
  name: string;
  version: string;
  nodes: number;
  pool: string;
}

export const api = {
  clusterStatus: () => request<ClusterStatus>("/cluster/status"),
  nodes: () => request<{ nodes: NodeRow[] }>("/nodes").then((r) => r.nodes),
  node: (id: string) => request<NodeRow>(`/nodes/${id}`),
  pauseNode: (id: string) =>
    request<{ ok: boolean }>(`/nodes/${id}/pause`, { method: "POST" }),
  drainNode: (id: string) =>
    request<{ ok: boolean }>(`/nodes/${id}/drain`, { method: "POST" }),
  runNodeShell: (nodeId: string, command: string, cwd = "", timeout = 60) =>
    request<ShellResult>(`/nodes/${nodeId}/shell`, {
      method: "POST",
      body: JSON.stringify({ command, cwd, timeout }),
    }),
  jobs: () => request<{ jobs: JobRow[] }>("/jobs").then((r) => r.jobs),
  job: (id: string) => request<JobRow>(`/jobs/${id}`),
  cancelJob: (id: string) =>
    request<{ ok: boolean }>(`/jobs/${id}`, { method: "DELETE" }),
  tasks: () => request<{ tasks: TaskRow[] }>("/tasks").then((r) => r.tasks),
  logs: (params?: { limit?: number; level?: string; source?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.level) qs.set("level", params.level);
    if (params?.source) qs.set("source", params.source);
    if (params?.q) qs.set("q", params.q);
    const q = qs.toString();
    return request<{ logs: LogRow[] }>(`/logs${q ? `?${q}` : ""}`).then((r) => r.logs);
  },
  libraries: () =>
    request<{ libraries: LibraryRow[] }>("/libraries").then((r) => r.libraries),
  installLibrary: (
    package_name: string,
    version: string,
    pool = "all",
    include_driver = true,
    node_ids?: string[],
  ) =>
    request<InstallLibraryResult>("/libraries/install", {
      method: "POST",
      body: JSON.stringify({ package_name, version, pool, include_driver, node_ids }),
    }),
  rebalance: () =>
    request<{ ok: boolean; migrations: number }>("/cluster/rebalance", {
      method: "POST",
    }),
  savings: () =>
    request<{
      estimated_monthly_savings_usd: number;
      utilized_cores: number;
      idle_cores: number;
      total_cores: number;
    }>("/metrics/savings"),
  sites: () =>
    request<{ sites: { site: string; nodes: number; healthy: number; tenant: string }[] }>(
      "/discovery/sites",
    ).then((r) => r.sites),
  mesh: () =>
    request<{
      site_id: string;
      relay: { listen: string; public: string; connections: number } | null;
      peers: MeshPeer[];
    }>("/mesh"),
  probeMesh: () => request<unknown>("/mesh/probe", { method: "POST" }),
  notebookStatus: () =>
    request<{
      workers_available: number;
      local_available: boolean;
      workers: { hostname: string; location: string }[];
    }>("/notebook/status"),
  executeNotebook: (code: string, language: "python" | "pyspark", mode = "mesh") =>
    request<{
      stdout: string;
      stderr: string;
      error: string | null;
      result: unknown;
      mode: string;
      node: string | null;
    }>("/notebook/execute", {
      method: "POST",
      body: JSON.stringify({ code, language, mode }),
    }),
  joinInfo: () =>
    request<{
      driver_grpc: string;
      agent_grpc: string;
      dashboard_port: number;
      relay_port: number;
      install: string;
      requirements: string[];
    }>("/cluster/join-info"),
  memoryPool: () =>
    request<{
      total_gb: number;
      free_gb: number;
      allocated_gb: number;
      utilization_pct: number;
      node_count: number;
      segment_count: number;
    }>("/memory/pool"),
  memoryAllocations: () =>
    request<{ allocations: MemoryAllocation[] }>("/memory/allocations").then((r) => r.allocations),
  allocateMemory: (size_gb: number, owner = "") =>
    request<{ ok: boolean; allocation?: MemoryAllocation }>("/memory/allocate", {
      method: "POST",
      body: JSON.stringify({ size_gb, owner }),
    }),
  releaseMemory: (allocation_id: string) =>
    request<{ ok: boolean }>(`/memory/allocations/${allocation_id}`, { method: "DELETE" }),
  schedulerBenchmark: (nodes = 1000, iterations = 50) =>
    request<{
      node_count: number;
      p99_ms: number;
      passed: boolean;
      mean_ms: number;
    }>(`/scheduler/benchmark?nodes=${nodes}&iterations=${iterations}`),
};

export interface MemoryAllocation {
  allocation_id: string;
  total_gb: number;
  owner: string;
  pinned: boolean;
  segments: { node_id: string; hostname: string; size_gb: number; location: string }[];
}

export interface ShellResult {
  ok: boolean;
  exit_code?: number;
  stdout?: string;
  stderr?: string;
  message?: string;
  error?: string;
  duration_seconds?: number;
  hostname?: string;
  node_id?: string;
}

export interface MeshPeer {
  site_id: string;
  relay_address: string;
  grpc_address: string;
  region: string;
  latency_ms: number;
  status: string;
}

export function streamUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/v1/stream`;
}
