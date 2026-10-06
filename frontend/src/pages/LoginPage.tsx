import { useState } from "react";
import { api, auth, ApiError, friendlyError } from "../api/client";
import { useApp } from "../lib/AppContext";

export default function LoginPage() {
  const { reloadIdentity } = useApp();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) { setErr("کلید API را وارد کنید."); return; }
    setBusy(true);
    setErr(null);
    auth.set(key); // validate before keeping it
    try {
      await api.me();
      await reloadIdentity();
    } catch (e2) {
      auth.clear();
      setErr(e2 instanceof ApiError ? friendlyError(e2) : String(e2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>سامانه CRM</h1>
        <p className="muted small">برای ورود، کلید API خود را وارد کنید. کلید فقط در همین نشست مرورگر نگه‌داشته می‌شود.</p>
        <label className="field">
          <span>کلید API</span>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
            placeholder="key-…" autoFocus dir="ltr" />
        </label>
        {err && <div className="error-state" style={{ textAlign: "right", padding: "8px 12px" }}>{err}</div>}
        <button className="btn btn-primary" disabled={busy} style={{ width: "100%", marginTop: 8 }}>
          {busy ? <><span className="spinner" /> در حال بررسی…</> : "ورود"}
        </button>
      </form>
    </div>
  );
}
