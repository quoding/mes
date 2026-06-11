import { create } from "zustand";
import type { FailureAlert, FailureAlertWsMessage } from "@/types/mes";

interface ToastEntry extends FailureAlertWsMessage {
  toastId: string;
}

interface AlertState {
  active: Record<number, FailureAlert>;
  toasts: ToastEntry[];
  wsStatus: "connecting" | "connected" | "disconnected";

  setActive: (alerts: FailureAlert[]) => void;
  applyMessage: (msg: FailureAlertWsMessage) => void;
  dismissToast: (toastId: string) => void;
  setWsStatus: (s: AlertState["wsStatus"]) => void;
}

export const useAlertStore = create<AlertState>((set) => ({
  active: {},
  toasts: [],
  wsStatus: "disconnected",

  setActive: (alerts) =>
    set(() => {
      const active: Record<number, FailureAlert> = {};
      for (const a of alerts) active[a.id] = a;
      return { active };
    }),

  applyMessage: (msg) =>
    set((state) => {
      const active = { ...state.active };
      if (msg.state === "RESOLVED") {
        delete active[msg.alert_id];
      } else {
        active[msg.alert_id] = {
          id: msg.alert_id,
          signature_id: msg.signature_id,
          name: msg.name,
          line_id: msg.line_id,
          severity: msg.severity,
          confidence: msg.confidence,
          state: msg.state,
          evidence: msg.evidence,
          raised_at: msg.raised_at,
          last_seen_at: msg.last_seen_at,
          resolved_at: msg.resolved_at,
          action: msg.action,
          equipment_ids: msg.equipment_ids,
        };
      }

      let toasts = state.toasts;
      if (msg.event === "RAISED" || msg.event === "RESOLVED") {
        toasts = [
          { ...msg, toastId: `${msg.alert_id}-${msg.event}-${Date.now()}` },
          ...state.toasts,
        ].slice(0, 5);
      }

      return { active, toasts };
    }),

  dismissToast: (toastId) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.toastId !== toastId) })),

  setWsStatus: (wsStatus) => set({ wsStatus }),
}));
