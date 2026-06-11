import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { useProcessStore } from "@/stores/processStore";
import { fmtValue, paramLabel, stationLabel } from "@/lib/labels";

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
  color = "#38bdf8",
  unit = "",
  height = 150,
}: RealtimeChartProps) {
  const key = `${lineId}:${station}:${param}`;
  const buf = useProcessStore((s) => s.buffers[key] ?? EMPTY_BUF);
  const latest = useProcessStore((s) => s.latest[key]);
  const gradId = `grad-${lineId}-${station}-${param}`;

  // Downsample for display
  const data = buf.filter((_, i) => i % 2 === 0).slice(-100);

  const isAnomaly =
    latest &&
    thresholdLow !== undefined &&
    thresholdHigh !== undefined &&
    (latest.value > thresholdHigh || latest.value < thresholdLow);

  const lineColor = isAnomaly ? "#fb7185" : color;

  return (
    <div className={`glass-card glass-card-hover p-3 ${isAnomaly ? "alert-critical-ring" : ""}`}>
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-[#e2e8f0] truncate">
            {stationLabel(station)} · {paramLabel(param)}
          </div>
          <div className="text-[10px] text-[#64748b] font-mono truncate">
            {station}.{param}
          </div>
        </div>
        <span className={`metric-num text-sm font-bold shrink-0 ${isAnomaly ? "text-[#fb7185]" : "text-white"}`}>
          {latest ? `${fmtValue(latest.value)} ${unit}` : "—"}
          {isAnomaly && " ⚠️"}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lineColor} stopOpacity={0.28} />
              <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2740" vertical={false} />
          <XAxis
            dataKey="time"
            tickFormatter={fmtTime}
            tick={{ fill: "#64748b", fontSize: 9 }}
            interval="preserveStartEnd"
            axisLine={{ stroke: "#1c2740" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#64748b", fontSize: 9 }}
            width={42}
            domain={["auto", "auto"]}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "rgba(13, 19, 34, 0.95)",
              border: "1px solid #1c2740",
              borderRadius: 8,
              fontSize: 11,
            }}
            labelFormatter={fmtTime}
            formatter={(v: number) => [`${fmtValue(v)} ${unit}`, paramLabel(param)]}
          />
          {thresholdHigh !== undefined && (
            <ReferenceLine
              y={thresholdHigh}
              stroke="#fb7185"
              strokeDasharray="4 4"
              strokeWidth={1}
              label={{ value: `상한 ${thresholdHigh}`, position: "insideTopRight", fill: "#fb7185", fontSize: 9 }}
            />
          )}
          {thresholdLow !== undefined && (
            <ReferenceLine
              y={thresholdLow}
              stroke="#fb7185"
              strokeDasharray="4 4"
              strokeWidth={1}
              label={{ value: `하한 ${thresholdLow}`, position: "insideBottomRight", fill: "#fb7185", fontSize: 9 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke={lineColor}
            fill={`url(#${gradId})`}
            dot={false}
            strokeWidth={1.6}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
