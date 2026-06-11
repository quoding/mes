import { useEffect, useRef } from "react";
import { api, WS_ALERTS_URL } from "@/lib/api";
import { useAlertStore } from "@/stores/alertStore";
import type { FailureAlert, FailureAlertWsMessage } from "@/types/mes";

export function useAlerts() {
  const wsRef = useRef<WebSocket | null>(null);
  const { setActive, applyMessage, setWsStatus } = useAlertStore();

  // Initial snapshot via REST
  useEffect(() => {
    let alive = true;
    api
      .get("/alerts/active")
      .then((r) => {
        if (alive) setActive(r.data as FailureAlert[]);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [setActive]);

  // Live updates via WebSocket
  useEffect(() => {
    let alive = true;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      if (!alive) return;
      setWsStatus("connecting");
      const ws = new WebSocket(WS_ALERTS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!alive) { ws.close(); return; }
        setWsStatus("connected");
      };

      ws.onmessage = (e) => {
        if (!alive) return;
        try {
          const msg: FailureAlertWsMessage = JSON.parse(e.data);
          applyMessage(msg);
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
  }, [applyMessage, setWsStatus]);
}
