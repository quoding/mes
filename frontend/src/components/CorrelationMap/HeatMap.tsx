import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CorrelationPair } from "@/types/mes";
import { paramLabel } from "@/lib/labels";

interface HeatMapProps {
  lineId?: number;
  station?: string;
}

function rToColor(r: number): string {
  const abs = Math.abs(r);
  if (abs >= 0.8) return r > 0 ? "#dc2626" : "#2563eb";
  if (abs >= 0.6) return r > 0 ? "#f97316" : "#60a5fa";
  if (abs >= 0.4) return r > 0 ? "var(--warn)" : "#93c5fd";
  return "var(--chip)";
}

export function HeatMap({ lineId = 1, station = "coating" }: HeatMapProps) {
  const { data, isLoading } = useQuery<CorrelationPair[]>({
    queryKey: ["correlation", lineId, station],
    queryFn: () =>
      api.get("/correlation/matrix", { params: { line_id: lineId, station, window_minutes: 30 } })
        .then((r) => r.data),
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="text-[var(--muted)] text-sm p-4">상관관계 계산 중…</div>;
  if (!data?.length) return <div className="text-[var(--muted)] text-sm p-4">데이터 부족 (30분 이후 표시)</div>;

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
            <div className="text-xs text-[var(--text)] truncate">
              {paramLabel(pair.param_a)} ↔ {paramLabel(pair.param_b)}
            </div>
            <div className="text-xs text-[var(--muted)]">{pair.interpretation}</div>
          </div>
          <div
            className={`text-xs shrink-0 ${pair.p_value < 0.05 ? "text-green-400" : "text-[var(--muted)]"}`}
            title={`p-value: ${pair.p_value.toExponential(2)}`}
          >
            {pair.p_value < 0.05 ? "유의" : "비유의"}
          </div>
        </div>
      ))}
      {/* 색상 범례 */}
      <div className="flex items-center gap-3 pt-2 mt-1 border-t border-[var(--border)] text-[10px] text-[var(--muted)]">
        <span>상관 강도:</span>
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-sm inline-block" style={{ background: "#dc2626" }} /> 강한 양(+)</span>
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-sm inline-block" style={{ background: "#2563eb" }} /> 강한 음(−)</span>
        <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-sm inline-block" style={{ background: "var(--chip)" }} /> 약함</span>
      </div>
    </div>
  );
}
