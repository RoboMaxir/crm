import { useEffect, useRef, useState, type ReactNode } from "react";
import { t as faT } from "../lib/format";

export function Badge({ children, color }: { children: ReactNode; color?: string }) {
  return <span className="badge" style={color ? { background: color, color: "#fff" } : undefined}>{children}</span>;
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const map: Record<string, string> = {
    new: "b-blue", contacted: "b-cyan", qualified: "b-green", unqualified: "b-gray",
    converted: "b-purple", lost: "b-red", won: "b-green", open: "b-blue",
    pending: "b-amber", completed: "b-green", cancelled: "b-gray",
    active: "b-green", inactive: "b-gray", archived: "b-gray",
    high: "b-red", urgent: "b-red", medium: "b-amber", low: "b-gray",
    critical: "b-red", none: "b-gray",
  };
  if (!status) return <span className="badge b-gray">—</span>;
  return <span className={`badge ${map[status] || "b-gray"}`}>{faT(status)}</span>;
}

export function RiskBadge({ level, score }: { level?: string | null; score?: number | null }) {
  if (!level || level === "none") return null;
  return (
    <span className={`badge ${level === "critical" || level === "high" ? "b-red" : level === "medium" ? "b-amber" : "b-gray"}`}
      title={score != null ? `risk_score=${score}` : undefined}>
      ریسک: {faT(level)}
    </span>
  );
}

export function Spinner() {
  return <div className="center muted"><span className="spinner" /> در حال بارگذاری…</div>;
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <p>{text}</p>
      {action}
    </div>
  );
}

export function ErrorState({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="error-state">
      <p>⚠ {text}</p>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>تلاش دوباره</button>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: {
  title: string; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="بستن">✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-title">
      <div>
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      <div className="row-gap">{actions}</div>
    </div>
  );
}

export function StatCard({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "good" | "bad" | "warn" }) {
  return (
    <div className={`stat-card ${tone ? `stat-${tone}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function ConfirmButton({ onConfirm, children, className = "btn btn-danger btn-sm" }: {
  onConfirm: () => void; children: ReactNode; className?: string;
}) {
  // two-step destructive confirm — no window.confirm
  const armed = useArmed();
  return (
    <button className={className} onClick={() => (armed.armed ? onConfirm() : armed.arm())}
      onBlur={armed.disarm}>
      {armed.armed ? "مطمئنی؟ دوباره بزن" : children}
    </button>
  );
}

import { useEffect, useRef, useState } from "react";
function useArmed(timeout = 3000) {
  const [armed, setArmed] = useState(false);
  const ref = useRef<number | null>(null);
  const arm = () => {
    setArmed(true);
    if (ref.current) window.clearTimeout(ref.current);
    ref.current = window.setTimeout(() => setArmed(false), timeout);
  };
  const disarm = () => setArmed(false);
  useEffect(() => () => { if (ref.current) window.clearTimeout(ref.current); }, []);
  return { armed, arm, disarm };
}
