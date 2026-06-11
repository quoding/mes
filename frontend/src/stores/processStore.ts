import { create } from "zustand";
import type { ProcessReading, ParamBuffer, AnomalyEvent } from "@/types/mes";

const BUFFER_SIZE = 200;

interface ProcessState {
  // Latest value per "line:station:param"
  latest: Record<string, { value: number; unit: string; time: string }>;
  // Rolling buffer for charts: "line:station:param" → [{time, value}]
  buffers: ParamBuffer;
  // Latest anomaly events (live)
  liveAnomalies: AnomalyEvent[];
  wsStatus: "connecting" | "connected" | "disconnected";

  updateReadings: (readings: ProcessReading[]) => void;
  addAnomalies: (events: AnomalyEvent[]) => void;
  setWsStatus: (s: ProcessState["wsStatus"]) => void;
}

export const useProcessStore = create<ProcessState>((set) => ({
  latest: {},
  buffers: {},
  liveAnomalies: [],
  wsStatus: "disconnected",

  updateReadings: (readings) =>
    set((state) => {
      const latest = { ...state.latest };
      const buffers = { ...state.buffers };

      for (const r of readings) {
        const key = `${r.line_id}:${r.station}:${r.param}`;
        latest[key] = { value: r.value, unit: r.unit, time: r.time };

        if (!buffers[key]) buffers[key] = [];
        const buf = [...buffers[key], { time: r.time, value: r.value }];
        buffers[key] = buf.length > BUFFER_SIZE ? buf.slice(-BUFFER_SIZE) : buf;
      }
      return { latest, buffers };
    }),

  addAnomalies: (events) =>
    set((state) => ({
      liveAnomalies: [...events, ...state.liveAnomalies].slice(0, 50),
    })),

  setWsStatus: (wsStatus) => set({ wsStatus }),
}));
