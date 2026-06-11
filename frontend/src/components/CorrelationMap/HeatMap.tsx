import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CorrelationPair } from "@/types/mes";

interface HeatMapProps {
  lineId?: number;
  station?: string;
}

function rToColor(r: number): string {
  const abs = Math.abs(r);
  if (abs >= 0.8) return r > 0 ? "#dc2626" : "#2563eb";
  if (abs >= 0.6) return r > 0 ? "#f97316" : "#60a5fa";
  if (abs >= 0.4) return r > 0 ? "#fbbf24" : "#93c5fd";
  return "#374151";
}

export function HeatMap({ lineId = 1, station = "coating" }: HeatMapProps) {
  const { data, isLoading } = useQuery<CorrelationPair[]>({
    queryKey: ["correlation", lineId, station],
    queryFn: () =>
      api.get("/correlation/matrix", { params: { line_id: lineId, station, window_minutes: 30 } })
        .then((r) => r.data),
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="text-[#6b7280] text-sm p-4">상관관계 계산 중…</div>;
  if (!data?.length) return <div className="text-[#6b7280] text-sm p-4">데이터 부족 (30분 이후 표시)</div>;

  const top = data.slice(0, 10);

  return (
    <div className="space-y-2">
      {top.map((pair, i) => (
        <div key={i} className="flex items-center gap-3">
          <div
            className="w-10 h-6 rounded text-center text-xs font-bold flex items-center justify-center shrink-0"
            style={{ backgroundColor: rToColor(pair.r), color: "#fff" }}
          >
            {pair.r.toFixed(2)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-mono text-[#e5e7eb] truncate">
              {pair.param_a} ↔ {pair.param_b}
            </div>
            <div className="text-xs text-[#6b7280]">{pair.interpretation}</div>
          </div>
          <div className={`text-xs ${pair.p_value < 0.05 ? "text-green-400" : "text-[#6b7280]"}`}>
            {pair.p_value < 0.05 ? "유의" : "비유의"}
          </div>
        </div>
      ))}
    </div>
  );
}
