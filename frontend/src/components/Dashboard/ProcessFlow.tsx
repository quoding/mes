import { Layers, Droplets, Scissors, RefreshCw } from "lucide-react";
import { useProcessStore } from "@/stores/processStore";
import { fmtValue } from "@/lib/labels";

// 스테이션별 대표 파라미터 + 상태 판정 범위 (백엔드 STATION_PARAMS 발췌)
const STATIONS = [
  {
    id: "coating", name: "코팅", desc: "슬러리 도포·건조", icon: Droplets,
    keyParam: "coating_thickness", unit: "μm",
    watch: [
      { param: "coating_thickness", low: 80, high: 120 },
      { param: "slurry_viscosity", low: 3000, high: 5000 },
      { param: "dry_temp_zone2", low: 100, high: 130 },
      { param: "tension_supply", low: 30, high: 50 },
    ],
  },
  {
    id: "calendering", name: "캘린더링", desc: "압연 — 밀도↑", icon: Layers,
    keyParam: "electrode_density", unit: "g/cm³",
    watch: [
      { param: "electrode_density", low: 1.5, high: 1.8 },
      { param: "roll_pressure", low: 200, high: 400 },
    ],
  },
  {
    id: "slitting", name: "슬리팅", desc: "폭 절단", icon: Scissors,
    keyParam: "slit_width_dev", unit: "mm",
    watch: [
      { param: "slit_width_dev", low: -0.1, high: 0.1 },
      { param: "tension", low: 20, high: 40 },
    ],
  },
  {
    id: "winding", name: "권취", desc: "롤 권취", icon: RefreshCw,
    keyParam: "tension", unit: "N",
    watch: [
      { param: "tension", low: 20, high: 35 },
      { param: "alignment_offset", low: -0.5, high: 0.5 },
    ],
  },
] as const;

type Status = "ok" | "warn" | "crit" | "idle";

const dotClass: Record<Status, string> = {
  ok: "dot dot-ok", warn: "dot dot-warn", crit: "dot dot-crit", idle: "dot dot-idle",
};

function judge(value: number, low: number, high: number): Status {
  const span = high - low;
  if (value > high + span * 0.15 || value < low - span * 0.15) return "crit";
  if (value > high || value < low) return "warn";
  return "ok";
}

const worse = (a: Status, b: Status): Status => {
  const rank: Status[] = ["idle", "ok", "warn", "crit"];
  return rank.indexOf(a) > rank.indexOf(b) ? a : b;
};

export function ProcessFlow({ lineId, running }: { lineId: number; running: boolean }) {
  const latest = useProcessStore((s) => s.latest);

  return (
    <div className="glass-card px-4 py-3">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-xs font-bold text-white">Line {lineId}</span>
        <span className="text-[10px] text-[#64748b]">롤투롤 전극 공정</span>
        <span className={`ml-auto text-[10px] ${running ? "text-[#34d399]" : "text-[#64748b]"}`}>
          {running ? "● RUNNING" : "○ STOPPED"}
        </span>
      </div>
      <div className="flex items-stretch">
        {STATIONS.map((st, i) => {
          const reading = latest[`${lineId}:${st.id}:${st.keyParam}`];
          let status: Status = "idle";
          if (running && reading) {
            status = "ok";
            for (const w of st.watch) {
              const r = latest[`${lineId}:${st.id}:${w.param}`];
              if (r) status = worse(status, judge(r.value, w.low, w.high));
            }
          }
          const Icon = st.icon;
          return (
            <div key={st.id} className="flex items-center flex-1 min-w-0">
              <div
                className={`flex-1 min-w-0 rounded-lg border px-3 py-2 transition-colors ${
                  status === "crit"
                    ? "border-[#fb7185]/50 bg-[#fb7185]/10 alert-critical-ring"
                    : status === "warn"
                      ? "border-[#fbbf24]/40 bg-[#fbbf24]/5"
                      : "border-[#1c2740] bg-[#0d1322]/60"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon size={14} className={status === "idle" ? "text-[#475569]" : "text-[#38bdf8]"} />
                  <span className="text-xs font-semibold text-white truncate">{st.name}</span>
                  <span className={`ml-auto ${dotClass[status]}`} />
                </div>
                <div className="metric-num text-sm font-bold text-[#e2e8f0] mt-1">
                  {reading && running ? fmtValue(reading.value) : "—"}
                  <span className="text-[10px] font-normal text-[#64748b] ml-1">{st.unit}</span>
                </div>
                <div className="text-[10px] text-[#64748b] truncate">{st.desc}</div>
              </div>
              {i < STATIONS.length - 1 && (
                <div className="w-6 shrink-0 px-1">
                  <div className={`flow-track ${running ? "" : "flow-track-paused"}`} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
