import { useEffect, useRef } from "react";
import { WS_URL } from "@/lib/api";
import { useProcessStore } from "@/stores/processStore";
import type { ProcessReading } from "@/types/mes";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const { updateReadings, setWsStatus } = useProcessStore();

  useEffect(() => {
    // `alive` prevents retry after cleanup. React 18 Strict Mode runs effects
    // twice in dev (mount→unmount→mount); without this the unmount's onclose
    // queues a retry that fires after the second mount, creating two competing
    // connections and the "closed before established" browser error.
    let alive = true;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      if (!alive) return;
      setWsStatus("connecting");
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!alive) { ws.close(); return; }
        setWsStatus("connected");
      };

      ws.onmessage = (e) => {
        if (!alive) return;
        try {
          const readings: ProcessReading[] = JSON.parse(e.data);
          updateReadings(readings);
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!alive) return;
        setWsStatus("disconnected");
        retryTimer = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      alive = false;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);
}
