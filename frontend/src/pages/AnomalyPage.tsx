import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AnomalyList } from "@/components/AnomalyPanel/AnomalyList";
import { HeatMap } from "@/components/CorrelationMap/HeatMap";
import type { AnomalyEvent } from "@/types/mes";

export default function AnomalyPage() {
  const [severity, setSeverity] = useState<string>("");
  const [lineId, setLineId] = useState<number | undefined>();
  const [hours, setHours] = useState(24);

  const { data: events = [], isLoading } = useQuery<AnomalyEvent[]>({
    queryKey: ["anomaly-events", lineId, severity, hours],
    queryFn: () =>
      api
        .get("/anomaly/events", {
          params: { hours, limit: 100, ...(lineId ? { line_id: lineId } : {}), ...(severity ? { severity } : {}) },
        })
        .then((r) => r.data),
    refetchInterval: 10_000,
  });

  const { data: summary } = useQuery({
    queryKey: ["anomaly-summary-24"],
    queryFn: () => api.get("/anomaly/summary", { params: { hours: 24 } }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">이상 탐지</h1>

      {/* Summary badges */}
      {summary && (
        <div className="flex gap-3 flex-wrap">
          {Object.entries(summary.by_severity as Record<string, number>).map(([sev, cnt]) => (
            <div
              key={sev}
              className={`px-4 py-2 rounded-xl text-sm font-bold border ${
                sev === "CRITICAL"
                  ? "bg-red-900/30 border-red-700 text-red-400"
                  : sev === "WARNING"
                  ? "bg-yellow-900/30 border-yellow-700 text-yellow-400"
                  : "bg-blue-900/30 border-blue-700 text-blue-400"
              }`}
            >
              {sev}: {cnt}건
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={lineId ?? ""}
          onChange={(e) => setLineId(e.target.value ? Number(e.target.value) : undefined)}
          className="bg-[#1f2937] text-[#9ca3af] text-sm rounded-lg px-3 py-2 outline-none"
        >
          <option value="">전체 라인</option>
          <option value="1">Line 1</option>
          <option value="2">Line 2</option>
        </select>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-[#1f2937] text-[#9ca3af] text-sm rounded-lg px-3 py-2 outline-none"
        >
          <option value="">전체 심각도</option>
          <option value="CRITICAL">CRITICAL</option>
          <option value="WARNING">WARNING</option>
          <option value="INFO">INFO</option>
        </select>
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="bg-[#1f2937] text-[#9ca3af] text-sm rounded-lg px-3 py-2 outline-none"
        >
          <option value={8}>최근 8시간</option>
          <option value={24}>최근 24시간</option>
          <option value={72}>최근 3일</option>
          <option value={168}>최근 1주</option>
        </select>
        <span className="text-sm text-[#6b7280]">{events.length}건</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          {isLoading ? (
            <div className="text-[#6b7280] text-sm">로딩 중…</div>
          ) : (
            <AnomalyList events={events} maxItems={50} />
          )}
        </div>

        <div>
          <h2 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wide">
            파라미터 상관관계
          </h2>
          <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4 space-y-4">
            <div>
              <div className="text-xs text-[#6b7280] mb-2">코팅 공정 (Line 1)</div>
              <HeatMap lineId={1} station="coating" />
            </div>
            <div>
              <div className="text-xs text-[#6b7280] mb-2">캘린더링 공정 (Line 1)</div>
              <HeatMap lineId={1} station="calendering" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
