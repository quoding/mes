import { ShieldAlert, Activity } from "lucide-react";
import { useAlertStore } from "@/stores/alertStore";
import { api } from "@/lib/api";

const severityStyle: Record<string, string> = {
  CRITICAL: "bg-[var(--crit)]/10 border-[var(--crit)]/40 text-[var(--crit-soft)] alert-critical-ring",
  WARNING: "bg-[var(--warn)]/8 border-[var(--warn)]/35 text-[var(--warn-soft)]",
};

export function AlertBanner() {
  const active = useAlertStore((s) => s.active);
  const alerts = Object.values(active).sort((a, b) => b.confidence - a.confidence);

  if (alerts.length === 0) {
    return (
      <div className="glass-card flex items-center gap-2.5 p-3 text-sm text-[var(--muted)]">
        <ShieldAlert size={16} className="text-[var(--ok)]" />
        고장 전조 신호 없음 — 상관관계 패턴 정상
        <span className="dot dot-ok ml-auto" />
      </div>
    );
  }

  const ack = async (id: number) => {
    await api.post(`/alerts/${id}/ack`);
  };

  return (
    <div className="space-y-2">
      {alerts.map((a) => (
        <div key={a.id} className={`p-3 rounded-xl border backdrop-blur fade-in-up ${severityStyle[a.severity] ?? severityStyle.WARNING}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold px-1.5 py-0.5 rounded bg-current/20 border border-current">
                  {a.severity}
                </span>
                <span className="text-xs text-[var(--muted2)]">Line {a.line_id}</span>
                <span className="text-sm font-semibold">{a.name ?? a.signature_id}</span>
                <span className="text-xs text-[var(--muted2)] flex items-center gap-1">
                  <Activity size={12} /> 신뢰도 {Math.round(a.confidence * 100)}%
                </span>
              </div>
              {a.action && <div className="text-xs mt-1 text-[#d1d5db]">권장 조치: {a.action}</div>}
              <div className="text-[10px] text-[var(--muted)] mt-1">
                최초 감지: {new Date(a.raised_at).toLocaleString("ko-KR")}
              </div>
            </div>
            {!a.acked_at && (
              <button
                onClick={() => ack(a.id)}
                className="shrink-0 text-xs px-2 py-1 rounded border border-current/40 hover:bg-current/10"
              >
                확인
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
