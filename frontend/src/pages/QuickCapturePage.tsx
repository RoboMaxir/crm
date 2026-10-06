import { useState } from "react";
import { api } from "../api/client";
import { mutate } from "../lib/hooks";
import { useApp } from "../lib/AppContext";
import { Field, PageTitle } from "../components/ui";
import { localToIso } from "../lib/format";

/** Quick Capture — Org + Contact + Lead + Next Action in ONE POST /quick/capture.
 *  Structured form now; later a NL→Intent parser can fill the same `intent` shape. */
export default function QuickCapturePage({ onDone }: { onDone?: (orgId: string) => void }) {
  const { can } = useApp();
  const [f, setF] = useState({
    orgName: "", industry: "", city: "", phone: "", website: "",
    contactFirst: "", contactLast: "", contactJob: "", contactPhone: "", contactEmail: "",
    leadTitle: "", leadSource: "manual", leadValue: "", leadScore: "0", leadNotes: "",
    naType: "follow_up", naSubject: "", naDue: "", naPriority: "medium",
  });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!can("create")) return;
    setBusy(true);
    setResult(null);
    const payload = {
      organization: {
        name: f.orgName.trim(), industry: f.industry || undefined, city: f.city || undefined,
        phone: f.phone || undefined, website: f.website || undefined, type: "prospect",
      },
      contact: f.contactFirst.trim() ? {
        first_name: f.contactFirst.trim(), last_name: f.contactLast.trim() || undefined,
        job_title: f.contactJob || undefined, phone: f.contactPhone || undefined, email: f.contactEmail || undefined,
      } : {},
      lead: {
        title: (f.leadTitle.trim() || `${f.orgName.trim()} — سرنخ جدید`),
        source: f.leadSource,
        estimated_value: Number(f.leadValue || 0),
        score: Number(f.leadScore || 0),
        notes: f.leadNotes || undefined,
      },
      next_action: f.naSubject.trim() ? {
        type: f.naType, subject: f.naSubject.trim(),
        due_at: localToIso(f.naDue), priority: f.naPriority,
      } : null,
    };
    const res = await mutate(() => api.quickCapture(payload), "ثبت شد ✔");
    setBusy(false);
    if (res) {
      setResult(`سازمان «${res.organization.name}» ${res.organization_created ? "ساخته شد" : "یافت شد (تکراری نبود)"} · لید ساخته شد${res.next_action ? " · اقدام بعدی ثبت شد" : ""}`);
      setF((s) => ({ ...s, orgName: "", leadTitle: "", naSubject: "" }));
      onDone?.(res.organization.id);
    }
  };

  if (!can("create")) {
    return <div className="error-state">نقش شما اجازه ثبت اطلاعات (create) را ندارد.</div>;
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <PageTitle title="ثبت سریع (Quick Capture)" subtitle="یک تماس/جلسه را در کمتر از یک دقیقه وارد CRM کنید — همه‌چیز در یک تراکنش." />
      <form className="card" onSubmit={submit}>
        <div className="form-grid">
          <Field label="نام شرکت / سازمان *"><input required value={f.orgName} onChange={set("orgName")} placeholder="مثلاً: کارخانه CNC البرز" /></Field>
          <Field label="صنعت"><input value={f.industry} onChange={set("industry")} /></Field>
          <Field label="شهر"><input value={f.city} onChange={set("city")} /></Field>
          <Field label="تلفن"><input dir="ltr" value={f.phone} onChange={set("phone")} /></Field>
          <Field label="وب‌سایت"><input dir="ltr" value={f.website} onChange={set("website")} /></Field>
        </div>
        <h4>مخاطب (اختیاری)</h4>
        <div className="form-grid">
          <Field label="نام"><input value={f.contactFirst} onChange={set("contactFirst")} /></Field>
          <Field label="نام خانوادگی"><input value={f.contactLast} onChange={set("contactLast")} /></Field>
          <Field label="سمت"><input value={f.contactJob} onChange={set("contactJob")} /></Field>
          <Field label="موبایل"><input dir="ltr" value={f.contactPhone} onChange={set("contactPhone")} /></Field>
          <Field label="ایمیل"><input dir="ltr" value={f.contactEmail} onChange={set("contactEmail")} /></Field>
        </div>
        <h4>سرنخ (Lead)</h4>
        <div className="form-grid">
          <Field label="عنوان سرنخ"><input value={f.leadTitle} onChange={set("leadTitle")} placeholder="خالی = خودکار از نام شرکت" /></Field>
          <Field label="منبع">
            <select value={f.leadSource} onChange={set("leadSource")}>
              {["manual", "referral", "website", "instagram", "telegram", "linkedin", "cold_outreach", "event", "existing_customer"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="ارزش تقریبی (ریال)"><input dir="ltr" inputMode="numeric" value={f.leadValue} onChange={set("leadValue")} /></Field>
          <Field label="امتیاز (۰ تا ۱۰۰)"><input dir="ltr" type="number" min={0} max={100} value={f.leadScore} onChange={set("leadScore")} /></Field>
          <div className="full"><Field label="یادداشت"><textarea rows={2} value={f.leadNotes} onChange={set("leadNotes")} /></Field></div>
        </div>
        <h4>اقدام بعدی (Next Action)</h4>
        <div className="form-grid">
          <Field label="نوع">
            <select value={f.naType} onChange={set("naType")}>
              {["follow_up", "call", "meeting", "email", "task", "demo", "proposal"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="عنوان کار"><input value={f.naSubject} onChange={set("naSubject")} placeholder="مثلاً: ارسال پیش‌فاکتور" /></Field>
          <Field label="مهلت"><input type="datetime-local" value={f.naDue} onChange={set("naDue")} /></Field>
          <Field label="اولویت">
            <select value={f.naPriority} onChange={set("naPriority")}>
              {["low", "medium", "high", "urgent"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </Field>
        </div>
        <div className="row-gap" style={{ marginTop: 10 }}>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? <><span className="spinner" /> در حال ثبت…</> : "ثبت یکجا"}
          </button>
          {result && <span className="small" style={{ color: "#15803d" }}>{result}</span>}
        </div>
      </form>
    </div>
  );
}
