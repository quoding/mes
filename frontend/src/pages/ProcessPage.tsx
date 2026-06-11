import { useState } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { RealtimeChart } from "@/components/ProcessLine/RealtimeChart";
import { useProcessStore } from "@/stores/processStore";

const STATIONS = ["coating", "calendering", "slitting", "winding"] as const;
type Station = typeof STATIONS[number];

const STATION_PARAMS: Record<Station, { param: string; low: number; high: number; unit: string; color: string }[]> = {
  coating: [
    { param: "line_speed", low: 15, high: 25, unit: "m/min", color: "var(--accent)" },
    { param: "coating_thickness", low: 80, high: 120, unit: "μm", color: "var(--ok)" },
    { param: "coating_weight", low: 15, high: 20, unit: "mg/cm²", color: "var(--warn)" },
    { param: "dry_temp_zone1", low: 80, high: 100, unit: "°C", color: "var(--crit)" },
    { param: "dry_temp_zone2", low: 100, high: 130, unit: "°C", color: "#dc2626" },
    { param: "dry_temp_zone3", low: 120, high: 150, unit: "°C", color: "#b91c1c" },
    { param: "tension_supply", low: 30, high: 50, unit: "N", color: "#8b5cf6" },
    { param: "tension_winding", low: 40, high: 60, unit: "N", color: "#a78bfa" },
    { param: "slurry_viscosity", low: 3000, high: 5000, unit: "cP", color: "#ec4899" },
  ],
  calendering: [
    { param: "roll_pressure", low: 200, high: 400, unit: "kN/m", color: "var(--accent)" },
    { param: "roll_temperature", low: 60, high: 80, unit: "°C", color: "var(--crit)" },
    { param: "electrode_density", low: 1.5, high: 1.8, unit: "g/cm³", color: "var(--ok)" },
    { param: "thickness_before", low: 140, high: 180, unit: "μm", color: "var(--warn)" },
    { param: "thickness_after", low: 80, high: 120, unit: "μm", color: "#8b5cf6" },
    { param: "line_speed", low: 10, high: 20, unit: "m/min", color: "var(--muted)" },
  ],
  slitting: [
    { param: "line_speed", low: 30, high: 50, unit: "m/min", color: "var(--accent)" },
    { param: "tension", low: 20, high: 40, unit: "N", color: "#8b5cf6" },
    { param: "slit_width_dev", low: -0.1, high: 0.1, unit: "mm", color: "var(--warn)" },
    { param: "blade_pressure", low: 10, high: 30, unit: "N", color: "var(--ok)" },
  ],
  winding: [
    { param: "tension", low: 20, high: 35, unit: "N", color: "var(--accent)" },
    { param: "winding_speed", low: 20, high: 40, unit: "m/min", color: "var(--ok)" },
    { param: "roll_diameter", low: 50, high: 500, unit: "mm", color: "var(--warn)" },
    { param: "alignment_offset", low: -0.5, high: 0.5, unit: "mm", color: "var(--crit)" },
  ],
};

export default function ProcessPage() {
  useWebSocket();
  const [lineId, setLineId] = useState(1);
  const [station, setStation] = useState<Station>("coating");
  const wsStatus = useProcessStore((s) => s.wsStatus);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4 flex-wrap">
        <h1 className="text-xl font-bold text-[var(--text-strong)]">공정 모니터</h1>

        {/* Line selector */}
        <div className="flex gap-2">
          {[1, 2].map((l) => (
            <button
              key={l}
              onClick={() => setLineId(l)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                lineId === l ? "bg-blue-600 text-white" : "bg-[var(--border)] text-[var(--muted2)] hover:text-[var(--text-strong)]"
              }`}
            >
              Line {l}
            </button>
          ))}
        </div>

        {/* Station selector */}
        <div className="flex gap-2 flex-wrap">
          {STATIONS.map((s) => (
            <button
              key={s}
              onClick={() => setStation(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize ${
                station === s ? "bg-[var(--chip)] text-[var(--text-strong)]" : "bg-[var(--border)] text-[var(--muted2)] hover:text-[var(--text-strong)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-1.5 text-xs text-[var(--muted)]">
          <span className={`w-2 h-2 rounded-full ${wsStatus === "connected" ? "bg-green-500" : "bg-red-500"}`} />
          {wsStatus}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {STATION_PARAMS[station].map(({ param, low, high, unit, color }) => (
          <RealtimeChart
            key={param}
            lineId={lineId}
            station={station}
            param={param}
            thresholdLow={low}
            thresholdHigh={high}
            unit={unit}
            color={color}
            height={180}
          />
        ))}
      </div>
    </div>
  );
}
