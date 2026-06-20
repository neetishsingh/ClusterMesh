import { useEffect, useState, useCallback } from "react";
import { api, ClusterStatus, streamUrl } from "./client";

export function useClusterStream(intervalMs = 3000) {
  const [cluster, setCluster] = useState<ClusterStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<Record<string, unknown> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.clusterStatus();
      setCluster(data);
    } catch {
      /* offline */
    }
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, intervalMs);
    return () => clearInterval(poll);
  }, [refresh, intervalMs]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let alive = true;

    const connect = () => {
      ws = new WebSocket(streamUrl());
      ws.onopen = () => alive && setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (alive) setTimeout(connect, 3000);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "cluster" && msg.data) setCluster(msg.data);
          if (msg.type === "event" && msg.data) setLastEvent(msg.data);
        } catch {
          /* ignore */
        }
      };
    };
    connect();
    return () => {
      alive = false;
      ws?.close();
    };
  }, []);

  return { cluster, connected, lastEvent, refresh };
}

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    reload();
    const id = setInterval(reload, intervalMs);
    return () => clearInterval(id);
  }, [reload, intervalMs]);

  return { data, loading, error, reload };
}
