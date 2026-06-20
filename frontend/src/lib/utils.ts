export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat().format(n);
}

export function formatUsd(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function stateColor(state: string): string {
  const s = state.toUpperCase();
  if (["HEALTHY", "RUNNING", "COMPLETED", "SUCCEEDED"].includes(s))
    return "bg-emerald-50 text-emerald-700 ring-emerald-600/20";
  if (["SUSPECTED", "PENDING", "QUEUED", "PAUSED"].includes(s))
    return "bg-amber-50 text-amber-700 ring-amber-600/20";
  if (["DEAD", "FAILED", "CANCELLED", "ERROR"].includes(s))
    return "bg-red-50 text-red-700 ring-red-600/20";
  return "bg-slate-100 text-slate-600 ring-slate-500/20";
}

export function logLevelColor(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
      return "text-red-600";
    case "WARN":
      return "text-amber-600";
    case "DEBUG":
      return "text-slate-400";
    default:
      return "text-mesh-600";
  }
}
