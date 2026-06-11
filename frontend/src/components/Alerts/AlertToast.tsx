import { useEffect } from "react";
import { AlertOctagon, CheckCircle2, X } from "lucide-react";
import { useAlertStore } from "@/stores/alertStore";

const TOAST_TTL_MS = 8000;

export function AlertToastContainer() {
  const toasts = useAlertStore((s) => s.toasts);
  const dismissToast = useAlertStore((s) => s.dismissToast);

  useEffect(() => {
    const timers = toasts.map((t) =>
      setTimeout(() => dismissToast(t.toastId), TOAST_TTL_MS)
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismissToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 w-80">
      {toasts.map((t) => {
        const isResolved = t.event === "RESOLVED";
        return (
          <div
            key={t.toastId}
            className={`p-3 rounded-lg border shadow-lg backdrop-blur fade-in-up ${
              isResolved
                ? "bg-green-900/80 border-green-700 text-green-200"
                : t.severity === "CRITICAL"
                ? "bg-red-900/80 border-red-700 text-red-200"
                : "bg-yellow-900/80 border-yellow-700 text-yellow-200"
            }`}
          >
            <div className="flex items-start gap-2">
              {isResolved ? (
                <CheckCircle2 size={18} className="shrink-0 mt-0.5" />
              ) : (
                <AlertOctagon size={18} className="shrink-0 mt-0.5" />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold">
                  {isResolved ? "고장 신호 해소" : "고장 전조 신호 감지"} — Line {t.line_id}
                </div>
                <div className="text-sm font-semibold mt-0.5">{t.name}</div>
                {!isResolved && t.action && (
                  <div className="text-xs mt-1 opacity-90">권장 조치: {t.action}</div>
                )}
              </div>
              <button onClick={() => dismissToast(t.toastId)} className="shrink-0 opacity-70 hover:opacity-100">
                <X size={14} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
