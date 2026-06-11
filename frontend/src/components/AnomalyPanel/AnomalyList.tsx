import { AlertTriangle, AlertCircle, Info } from "lucide-react";
import type { AnomalyEvent } from "@/types/mes";

const severityConfig = {
  CRITICAL: {
    icon: AlertCircle,
    color: "text-red-400",
    bg: "bg-red-900/20 border-red-800",
    badge: "bg-red-500",
  },
  WARNING: {
    icon: AlertTriangle,
    color: "text-yellow-400",
    bg: "bg-yellow-900/20 border-yellow-800",
    badge: "bg-yellow-500",
  },
  INFO: {
    icon: Info,
    color: "text-blue-400",
    bg: "bg-blue-900/20 border-blue-800",
    badge: "bg-blue-500",
  },
};

interface AnomalyListProps {
  events: AnomalyEvent[];
  maxItems?: number;
}

export function AnomalyList({ events, maxItems = 20 }: AnomalyListProps) {
  const visible = events.slice(0, maxItems);

  if (visible.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-[#6b7280] text-sm">
        이상 이벤트 없음 ✅
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {visible.map((ev, i) => {
        const cfg = severityConfig[ev.severity] ?? severityConfig.INFO;
        const Icon = cfg.icon;
        const time = new Date(ev.detected_at).toLocaleString("ko-KR", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        });
        return (
          <div
            key={ev.id ?? i}
            className={`flex items-start gap-3 p-3 rounded-lg border ${cfg.bg}`}
          >
            <Icon size={16} className={`${cfg.color} shrink-0 mt-0.5`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${cfg.badge} text-white`}>
                  {ev.severity}
                </span>
                <span className="text-xs text-[#9ca3af]">Line {ev.line_id}</span>
                <span className="text-xs font-mono text-[#e5e7eb]">
                  {ev.station}.{ev.param}
                </span>
              </div>
              <div className="text-xs text-[#9ca3af] mt-1">
                측정값: <span className="text-white font-mono">{ev.value.toFixed(3)}</span>
                {ev.threshold_high !== null && (
                  <span className="ml-2">
                    범위: {ev.threshold_low?.toFixed(1)} ~ {ev.threshold_high?.toFixed(1)}
                  </span>
                )}
                <span className="ml-2">{time}</span>
              </div>
              {ev.pattern_type && (
                <div className="text-xs text-[#6b7280] mt-0.5">패턴: {ev.pattern_type}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
