import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { useProcessStore } from "@/stores/processStore";

// Stable empty reference — prevents Zustand getSnapshot from returning a new
// array every render when the buffer key doesn't exist yet (infinite loop).
const EMPTY_BUF: { time: string; value: number }[] = [];

// Module-level to avoid re-definition on every render
const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

interface RealtimeChartProps {
  lineId: number;
  station: string;
  param: string;
  thresholdLow?: number;
  thresholdHigh?: number;
  color?: string;
  unit?: string;
  height?: number;
}

export function RealtimeChart({
  lineId,
  station,
  param,
  thresholdLow,
  thresholdHigh,
  color = "#3b82f6",
  unit = "",
  height = 160,
}: RealtimeChartProps) {
  const key = `${lineId}:${station}:${param}`;
  const buf = useProcessStore((s) => s.buffers[key] ?? EMPTY_BUF);
  const latest = useProcessStore((s) => s.latest[key]);

  // Downsample for display
  const data = buf.filter((_, i) => i % 2 === 0).slice(-100);

  const isAnomaly =
    latest &&
    thresholdLow !== undefined &&
    thresholdHigh !== undefined &&
    (latest.value > thresholdHigh || latest.value < thresholdLow);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[#9ca3af] font-mono">
          {station}.{param}
        </span>
        <span className={`text-sm font-bold ${isAnomaly ? "text-red-400" : "text-white"}`}>
          {latest ? `${latest.value.toFixed(2)} ${unit}` : "—"}
          {isAnomaly && " ⚠️"}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="time"
            tickFormatter={fmtTime}
            tick={{ fill: "#6b7280", fontSize: 9 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 9 }}
            width={42}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #1f2937", fontSize: 11 }}
            labelFormatter={fmtTime}
            formatter={(v: number) => [`${v.toFixed(3)} ${unit}`, param]}
          />
          {thresholdHigh !== undefined && (
            <ReferenceLine y={thresholdHigh} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1} />
          )}
          {thresholdLow !== undefined && (
            <ReferenceLine y={thresholdLow} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1} />
          )}
          <Line
            type="monotone"
            dataKey="value"
            stroke={isAnomaly ? "#ef4444" : color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
