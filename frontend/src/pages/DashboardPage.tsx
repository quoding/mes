import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlerts } from "@/hooks/useAlerts";
import { useProcessStore } from "@/stores/processStore";
import { KpiCard } from "@/components/Dashboard/KpiCard";
import { RealtimeChart } from "@/components/ProcessLine/RealtimeChart";
import { AnomalyList } from "@/components/AnomalyPanel/AnomalyList";
import { AgentChat } from "@/components/AgentChat/AgentChat";
import { HeatMap } from "@/components/CorrelationMap/HeatMap";
import { AlertBanner } from "@/components/Alerts/AlertBanner";
import { AlertToastContainer } from "@/components/Alerts/AlertToast";

export default function DashboardPage() {
  useWebSocket();
  useAlerts();

  const wsStatus = useProcessStore((s) => s.wsStatus);
  const liveAnomalies = useProcessStore((s) => s.liveAnomalies);

  const [simLoading, setSimLoading] = useState(false);

  const { data: simStatus, refetch: refetchSim } = useQuery({
    queryKey: ["simulator-status"],
    queryFn: () => api.get("/process/simulator/status").then((r) => r.data as { running: boolean }),
    refetchInterval: 5_000,
  });

  const toggleSimulator = useCallback(async () => {
    if (simLoading) return;
    setSimLoading(true);
    try {
      const endpoint = simStatus?.running ? "/process/simulator/stop" : "/process/simulator/start";
      await api.post(endpoint);
      await refetchSim();
    } finally {
      setSimLoading(false);
    }
  }, [simStatus?.running, simLoading, refetchSim]);

  const { data: anomalySummary } = useQuery({
    queryKey: ["anomaly-summary"],
    queryFn: () => api.get("/anomaly/summary", { params: { hours: 8 } }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: anomalyEvents } = useQuery({
    queryKey: ["anomaly-events"],
    queryFn: () => api.get("/anomaly/events", { params: { hours: 24, limit: 20 } }).then((r) => r.data),
    refetchInterval: 15_000,
  });

  const criticalCount = anomalySummary?.by_severity?.CRITICAL ?? 0;
  const warningCount = anomalySummary?.by_severity?.WARNING ?? 0;
  const allEvents = [...liveAnomalies, ...(anomalyEvents ?? [])].slice(0, 20);

  return (
    <div className="p-6 space-y-6">
      <AlertToastContainer />
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">PNT Smart Factory Monitor</h1>
          <p className="text-sm text-[#6b7280]">롤투롤 2차전지 전극 제조공정 모니터링</p>
        </div>
        <div className="flex items-center gap-4">
          {/* Simulator toggle */}
          <button
            onClick={toggleSimulator}
            disabled={simLoading}
            className={`
              flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold
              transition-all duration-150 disabled:opacity-50
              ${simStatus?.running
                ? "bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25"
                : "bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25"
              }
            `}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${simStatus?.running ? "bg-red-400 animate-pulse" : "bg-gray-500"}`} />
            {simLoading ? "…" : simStatus?.running ? "시뮬레이터 정지" : "시뮬레이터 시작"}
          </button>

          {/* WS status */}
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                wsStatus === "connected" ? "bg-green-500" : wsStatus === "connecting" ? "bg-yellow-500 animate-pulse" : "bg-red-500"
              }`}
            />
            <span className="text-[#9ca3af]">
              {wsStatus === "connected" ? "실시간 연결" : wsStatus === "connecting" ? "연결 중…" : "연결 끊김"}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Line 1 가동"
          value="가동 중"
          status="ok"
          sub="코팅 → 캘린더링 → 슬리팅 → 권취"
        />
        <KpiCard
          title="Line 2 가동"
          value="가동 중"
          status="ok"
          sub="정상 범위 내"
        />
        <KpiCard
          title="이상 (24h)"
          value={criticalCount + warningCount}
          status={criticalCount > 0 ? "critical" : warningCount > 2 ? "warn" : "ok"}
          sub={`CRITICAL: ${criticalCount} | WARNING: ${warningCount}`}
        />
        <KpiCard
          title="예지보전 위험"
          value={criticalCount > 0 ? "고위험" : warningCount > 0 ? "중위험" : "정상"}
          status={criticalCount > 0 ? "critical" : warningCount > 0 ? "warn" : "ok"}
          sub="AI 분석 기반"
        />
      </div>

      {/* Layer 4 — Failure precursor alerts */}
      <div>
        <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
          고장 전조 신호 (상관관계 기반)
        </h2>
        <AlertBanner />
      </div>

      {/* Real-time Charts — Line 1 Coating key params */}
      <div>
        <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
          Line 1 — 코팅 공정 실시간
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <RealtimeChart lineId={1} station="coating" param="tension_supply" thresholdLow={30} thresholdHigh={50} unit="N" color="#3b82f6" />
          <RealtimeChart lineId={1} station="coating" param="coating_thickness" thresholdLow={80} thresholdHigh={120} unit="μm" color="#10b981" />
          <RealtimeChart lineId={1} station="coating" param="slurry_viscosity" thresholdLow={3000} thresholdHigh={5000} unit="cP" color="#f59e0b" />
          <RealtimeChart lineId={1} station="coating" param="dry_temp_zone2" thresholdLow={100} thresholdHigh={130} unit="°C" color="#ef4444" />
          <RealtimeChart lineId={1} station="calendering" param="roll_pressure" thresholdLow={200} thresholdHigh={400} unit="kN/m" color="#8b5cf6" />
          <RealtimeChart lineId={1} station="calendering" param="electrode_density" thresholdLow={1.5} thresholdHigh={1.8} unit="g/cm³" color="#ec4899" />
        </div>
      </div>

      {/* Bottom: Anomaly + Agent + Correlation */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1">
          <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
            이상 탐지 (최근 24h)
          </h2>
          <div className="max-h-96 overflow-y-auto space-y-2">
            <AnomalyList events={allEvents} maxItems={10} />
          </div>
        </div>

        <div className="xl:col-span-1">
          <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
            파라미터 상관관계 (코팅 30min)
          </h2>
          <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
            <HeatMap lineId={1} station="coating" />
          </div>
        </div>

        <div className="xl:col-span-1 h-96">
          <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
            공정 AI 에이전트
          </h2>
          <div className="h-[360px]">
            <AgentChat />
          </div>
        </div>
      </div>
    </div>
  );
}
