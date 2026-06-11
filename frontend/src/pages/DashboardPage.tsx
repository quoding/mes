import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, Square } from "lucide-react";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlerts } from "@/hooks/useAlerts";
import { useProcessStore } from "@/stores/processStore";
import { KpiCard } from "@/components/Dashboard/KpiCard";
import { ProcessFlow } from "@/components/Dashboard/ProcessFlow";
import { DemoPanel } from "@/components/Dashboard/DemoPanel";
import { RealtimeChart } from "@/components/ProcessLine/RealtimeChart";
import { AnomalyList } from "@/components/AnomalyPanel/AnomalyList";
import { AgentChat } from "@/components/AgentChat/AgentChat";
import { HeatMap } from "@/components/CorrelationMap/HeatMap";
import { AlertBanner } from "@/components/Alerts/AlertBanner";
import { AlertToastContainer } from "@/components/Alerts/AlertToast";

function LiveClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="text-right">
      <div className="metric-num text-lg font-bold text-white leading-tight">
        {now.toLocaleTimeString("ko-KR", { hour12: false })}
      </div>
      <div className="text-[10px] text-[#64748b]">
        {now.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" })}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  useWebSocket();
  useAlerts();

  const wsStatus = useProcessStore((s) => s.wsStatus);
  const liveAnomalies = useProcessStore((s) => s.liveAnomalies);
  const thicknessBuf = useProcessStore((s) => s.buffers["1:coating:coating_thickness"]);
  const densityBuf = useProcessStore((s) => s.buffers["1:calendering:electrode_density"]);

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
    queryFn: () => api.get("/anomaly/summary", { params: { hours: 24 } }).then((r) => r.data),
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
  const running = simStatus?.running ?? false;

  const spark = (buf?: { value: number }[]) => buf?.slice(-40).map((d) => d.value);

  return (
    <div className="p-6 space-y-5 max-w-[1800px] mx-auto">
      <AlertToastContainer />

      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">
            PNT Smart Factory Monitor
          </h1>
          <p className="text-xs text-[#64748b] mt-0.5">
            롤투롤 2차전지 전극 공정 — 실시간 설비 모니터링 · 고장 전조 탐지
          </p>
        </div>
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={
                wsStatus === "connected" ? "dot dot-ok" : wsStatus === "connecting" ? "dot dot-warn" : "dot dot-crit"
              }
            />
            <span className="text-[#7c8db5]">
              {wsStatus === "connected" ? "실시간 연결" : wsStatus === "connecting" ? "연결 중…" : "연결 끊김"}
            </span>
          </div>
          <button
            onClick={toggleSimulator}
            disabled={simLoading}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold
              transition-all duration-150 disabled:opacity-50 border
              ${running
                ? "bg-[#fb7185]/10 text-[#fb7185] border-[#fb7185]/30 hover:bg-[#fb7185]/20"
                : "bg-[#34d399]/10 text-[#34d399] border-[#34d399]/30 hover:bg-[#34d399]/20"
              }`}
          >
            {running ? <Square size={12} /> : <Play size={12} />}
            {simLoading ? "처리 중…" : running ? "시뮬레이터 정지" : "시뮬레이터 시작"}
          </button>
          <LiveClock />
        </div>
      </div>

      {/* ── 공정 흐름 파이프라인 ── */}
      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
        <ProcessFlow lineId={1} running={running} />
        <ProcessFlow lineId={2} running={running} />
      </div>

      {/* ── KPI ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="코팅 두께 (Line 1)"
          value={thicknessBuf?.length ? thicknessBuf[thicknessBuf.length - 1].value.toFixed(1) : "—"}
          unit="μm"
          status="ok"
          sub="정상범위 80~120"
          spark={spark(thicknessBuf)}
        />
        <KpiCard
          title="전극 밀도 (Line 1)"
          value={densityBuf?.length ? densityBuf[densityBuf.length - 1].value.toFixed(3) : "—"}
          unit="g/cm³"
          status="ok"
          sub="정상범위 1.5~1.8"
          spark={spark(densityBuf)}
        />
        <KpiCard
          title="이상 이벤트 (24h)"
          value={criticalCount + warningCount}
          status={criticalCount > 0 ? "critical" : warningCount > 2 ? "warn" : "ok"}
          sub={`CRITICAL ${criticalCount} · WARNING ${warningCount}`}
        />
        <KpiCard
          title="설비 리스크"
          value={criticalCount > 0 ? "고위험" : warningCount > 0 ? "관찰" : "안정"}
          status={criticalCount > 0 ? "critical" : warningCount > 0 ? "warn" : "ok"}
          sub="24h 이상 빈도 기반"
        />
      </div>

      {/* ── Layer 4 alerts ── */}
      <div>
        <h2 className="section-title mb-3">고장 전조 신호 — Layer 4 상관 시그니처</h2>
        <AlertBanner />
      </div>

      {/* ── Charts + Demo ── */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <div className="xl:col-span-3">
          <h2 className="section-title mb-3">Line 1 — 핵심 파라미터 실시간</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
            <RealtimeChart lineId={1} station="coating" param="coating_thickness" thresholdLow={80} thresholdHigh={120} unit="μm" color="#38bdf8" />
            <RealtimeChart lineId={1} station="coating" param="slurry_viscosity" thresholdLow={3000} thresholdHigh={5000} unit="cP" color="#a78bfa" />
            <RealtimeChart lineId={1} station="coating" param="dry_temp_zone2" thresholdLow={100} thresholdHigh={130} unit="°C" color="#fbbf24" />
            <RealtimeChart lineId={1} station="coating" param="tension_supply" thresholdLow={30} thresholdHigh={50} unit="N" color="#34d399" />
            <RealtimeChart lineId={1} station="calendering" param="roll_pressure" thresholdLow={200} thresholdHigh={400} unit="kN/m" color="#818cf8" />
            <RealtimeChart lineId={1} station="calendering" param="electrode_density" thresholdLow={1.5} thresholdHigh={1.8} unit="g/cm³" color="#f472b6" />
          </div>
        </div>
        <div className="xl:col-span-1">
          <h2 className="section-title mb-3">데모 시나리오</h2>
          <DemoPanel />
        </div>
      </div>

      {/* ── Bottom: Anomaly + Correlation + Agent ── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div>
          <h2 className="section-title mb-3">이상 탐지 이벤트 (24h)</h2>
          <div className="max-h-96 overflow-y-auto pr-1">
            <AnomalyList events={allEvents} maxItems={10} />
          </div>
        </div>
        <div>
          <h2 className="section-title mb-3">파라미터 상관관계 (코팅 · 30분)</h2>
          <div className="glass-card p-4">
            <HeatMap lineId={1} station="coating" />
          </div>
        </div>
        <div>
          <h2 className="section-title mb-3">공정 AI 에이전트</h2>
          <div className="h-[400px]">
            <AgentChat />
          </div>
        </div>
      </div>
    </div>
  );
}
