interface KpiCardProps {
  title: string;
  value: string | number;
  unit?: string;
  status?: "ok" | "warn" | "critical";
  sub?: string;
  /** 최근 값 배열 — 있으면 미니 스파크라인 표시 */
  spark?: number[];
}

const statusColor = {
  ok: "text-[var(--ok)]",
  warn: "text-[var(--warn)]",
  critical: "text-[var(--crit)]",
};

const sparkStroke = { ok: "var(--ok)", warn: "var(--warn)", critical: "var(--crit)" };

function Sparkline({ values, stroke }: { values: number[]; stroke: string }) {
  if (values.length < 2) return null;
  const w = 72, h = 26;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="opacity-70">
      {/* SVG 속성은 var()를 못 받으므로 style로 적용 */}
      <polyline points={pts} fill="none" style={{ stroke }} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function KpiCard({ title, value, unit, status = "ok", sub, spark }: KpiCardProps) {
  return (
    <div className={`glass-card glass-card-hover p-4 ${status === "critical" ? "alert-critical-ring" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] text-[var(--muted2)] tracking-wide mb-1">{title}</div>
          <div className={`metric-num text-2xl font-bold ${statusColor[status]}`}>
            {value}
            {unit && <span className="text-sm font-normal text-[var(--muted)] ml-1">{unit}</span>}
          </div>
          {sub && <div className="text-[10px] text-[var(--muted)] mt-1 truncate">{sub}</div>}
        </div>
        {spark && spark.length > 1 && (
          <div className="shrink-0 mt-1">
            <Sparkline values={spark} stroke={sparkStroke[status]} />
          </div>
        )}
      </div>
    </div>
  );
}
