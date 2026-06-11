interface KpiCardProps {
  title: string;
  value: string | number;
  unit?: string;
  status?: "ok" | "warn" | "critical";
  sub?: string;
}

const statusColor = {
  ok: "text-green-400",
  warn: "text-yellow-400",
  critical: "text-red-400",
};

export function KpiCard({ title, value, unit, status = "ok", sub }: KpiCardProps) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="text-xs text-[#6b7280] uppercase tracking-wide mb-1">{title}</div>
      <div className={`text-3xl font-bold ${statusColor[status]}`}>
        {value}
        {unit && <span className="text-lg font-normal text-[#9ca3af] ml-1">{unit}</span>}
      </div>
      {sub && <div className="text-xs text-[#6b7280] mt-1">{sub}</div>}
    </div>
  );
}
