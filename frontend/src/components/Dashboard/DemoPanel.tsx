import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FlaskConical, Gauge } from "lucide-react";
import { api } from "@/lib/api";

// 고장 시나리오 → 기대되는 Layer 4 시그니처 (E2E 테스트로 검증된 탐지 지연)
const SCENARIOS = [
  { type: "PRESSURE_OSC", name: "베어링 마모", expected: "BEARING_WEAR", eta: "~40초", severity: "crit" },
  { type: "TEMP_DEVIATION", name: "히터 제어 이상", expected: "HEATER_FAULT", eta: "~10초", severity: "crit" },
  { type: "THICKNESS_DRIFT", name: "다이 갭 마모", expected: "GAP_WEAR", eta: "~4분", severity: "warn" },
  { type: "VISCOSITY_RISE", name: "슬러리 열화", expected: "SLURRY_DEGRADE", eta: "~3분", severity: "warn" },
  { type: "TENSION_SPIKE", name: "장력 급변", expected: "Layer 1 즉시", eta: "~1초", severity: "warn" },
] as const;

interface EngineStatus {
  [line: string]: { warmed_up: boolean; samples: number; min_samples: number };
}

export function DemoPanel() {
  const [injected, setInjected] = useState<string | null>(null);

  const { data: engine } = useQuery<EngineStatus>({
    queryKey: ["engine-status"],
    queryFn: () => api.get("/alerts/engine-status").then((r) => r.data),
    refetchInterval: 10_000,
  });

  const inject = useMutation({
    mutationFn: (type: string) =>
      api.post("/process/simulator/inject", null, { params: { anomaly_type: type, line_id: 1 } }),
    onSuccess: (_, type) => {
      setInjected(type);
      setTimeout(() => setInjected(null), 4000);
    },
  });

  const line1 = engine?.["1"];
  const warmupPct = line1 ? Math.min(100, Math.round((line1.samples / line1.min_samples) * 100)) : 0;

  return (
    <div className="glass-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <FlaskConical size={14} className="text-[#38bdf8]" />
        <span className="text-xs font-bold text-white">고장 시나리오 데모</span>
        <span className="text-[10px] text-[#64748b]">Line 1에 주입 → 탐지 과정 관찰</span>
      </div>

      {/* Layer 4 워밍업 게이지 */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px] text-[#7c8db5]">
          <span className="flex items-center gap-1">
            <Gauge size={11} /> Layer 4 베이스라인 학습
          </span>
          <span className="metric-num">
            {line1?.warmed_up ? "준비 완료" : `${warmupPct}% (워밍업 중)`}
          </span>
        </div>
        <div className="h-1.5 rounded-full bg-[#1c2740] overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              line1?.warmed_up
                ? "bg-gradient-to-r from-[#34d399] to-[#38bdf8]"
                : "bg-gradient-to-r from-[#38bdf8] to-[#6366f1]"
            }`}
            style={{ width: `${warmupPct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-1.5">
        {SCENARIOS.map((s) => (
          <button
            key={s.type}
            onClick={() => inject.mutate(s.type)}
            disabled={inject.isPending}
            className={`group flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-left transition-all
              ${injected === s.type
                ? "border-[#34d399]/60 bg-[#34d399]/10"
                : "border-[#1c2740] bg-[#0d1322]/60 hover:border-[#38bdf8]/40 hover:bg-[#38bdf8]/5"}
              disabled:opacity-50`}
          >
            <span className={`dot ${s.severity === "crit" ? "dot-crit" : "dot-warn"} shrink-0`} />
            <span className="text-xs text-white font-medium w-24 shrink-0">{s.name}</span>
            <span className="text-[10px] text-[#64748b] truncate flex-1">
              → {s.expected}
            </span>
            <span className="text-[10px] metric-num text-[#7c8db5] shrink-0">
              {injected === s.type ? "주입됨 ✓" : s.eta}
            </span>
          </button>
        ))}
      </div>
      <p className="text-[10px] text-[#64748b] leading-relaxed">
        탐지 지연은 E2E 테스트 실측값. 시그니처 탐지는 베이스라인 학습 완료 후 동작합니다.
      </p>
    </div>
  );
}
