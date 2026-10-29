import { useStore } from "../store";

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <div className="toast-main">
            <b>{t.kind === "error" ? "Error: " : t.kind === "warn" ? "Check: " : ""}</b>
            {t.text}
            {t.details && (
              <ul>
                {t.details.slice(0, 8).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
                {t.details.length > 8 && <li>…and {t.details.length - 8} more</li>}
              </ul>
            )}
          </div>
          <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss">×</button>
        </div>
      ))}
    </div>
  );
}
