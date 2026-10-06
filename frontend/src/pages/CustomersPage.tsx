import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi, mutate } from "../lib/hooks";
import { useApp } from "../lib/AppContext";
import { Spinner, ErrorState, EmptyState, StatusBadge, Modal, Field, ConfirmButton, PageTitle } from "../components/ui";
import { fmtDate, t } from "../lib/format";
import type { Organization, Contact } from "../api/types";

type Tab = "orgs" | "contacts";

export default function CustomersPage() {
  const [tab, setTab] = useState<Tab>("orgs");
  return (
    <div>
      <PageTitle title="مشتریان" subtitle="سازمان‌ها و مخاطبان" actions={
        <div className="row-gap">
          <button className={`btn btn-sm ${tab === "orgs" ? "btn-primary" : ""}`} onClick={() => setTab("orgs")}>سازمان‌ها</button>
          <button className={`btn btn-sm ${tab === "contacts" ? "btn-primary" : ""}`} onClick={() => setTab("contacts")}>مخاطبان</button>
        </div>
      } />
      {tab === "orgs" ? <OrgTable /> : <ContactTable />}
    </div>
  );
}

// ------------------------------------------------------------------ orgs
function OrgTable() {
  const { can } = useApp();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const { state, reload } = useApi(() => api.listOrgs({ q: q || undefined, type: type || undefined, page, per_page: 25 }), [q, type, page]);

  return (
    <div>
      <div className="row-gap" style={{ marginBottom: 10 }}>
        <div className="searchbox"><input placeholder="جستجوی نام…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
        <select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
          <option value="">همه انواع</option>
          {["customer", "prospect", "partner", "vendor", "other"].map((x) => <option key={x} value={x}>{t(x)}</option>)}
        </select>
        {can("create") && <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>+ سازمان جدید</button>}
      </div>

      {state.loading ? <Spinner /> : state.error ? <ErrorState text={state.error} onRetry={reload} /> : !state.data || state.data.items.length === 0
        ? <EmptyState text="سازمانی یافت نشد." action={can("create") ? <button className="btn btn-sm" onClick={() => setCreating(true)}>ایجاد اولین سازمان</button> : undefined} />
        : (
          <>
            <table className="tbl">
              <thead><tr><th>نام</th><th>نوع</th><th>شهر</th><th>صنعت</th><th>تلفن</th><th>برچسب‌ها</th><th></th></tr></thead>
              <tbody>
                {state.data.items.map((o) => (
                  <tr key={o.id}>
                    <td><Link to={`/customers/${o.id}`}><b>{o.name}</b></Link></td>
                    <td><StatusBadge status={o.type} /></td>
                    <td>{o.city || "—"}</td>
                    <td>{o.industry || "—"}</td>
                    <td dir="ltr">{o.phone || "—"}</td>
                    <td>{(o.tags || []).map((tg) => <span key={tg} className="badge b-gray" style={{ marginLeft: 4 }}>{tg}</span>)}</td>
                    <td>{can("delete") && <ConfirmButton onConfirm={async () => { await mutate(() => api.deleteOrg(o.id), "حذف شد"); reload(); }}>حذف</ConfirmButton>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={state.data.page} pages={state.data.pages} onPage={setPage} />
          </>
        )}
      {creating && <OrgForm onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}
    </div>
  );
}

function OrgForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: "", legal_name: "", type: "prospect", industry: "", city: "", phone: "", email: "", website: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const body: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) if (v.trim()) body[k] = v.trim();
    const res = await mutate(() => api.createOrg(body), "سازمان ساخته شد ✔");
    setBusy(false);
    if (res) onSaved();
  };
  return (
    <Modal title="سازمان جدید" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="نام *"><input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="نام حقوقی"><input value={f.legal_name} onChange={(e) => setF({ ...f, legal_name: e.target.value })} /></Field>
          <Field label="نوع">
            <select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
              {["customer", "prospect", "partner", "vendor", "other"].map((x) => <option key={x} value={x}>{t(x)}</option>)}
            </select>
          </Field>
          <Field label="صنعت"><input value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} /></Field>
          <Field label="شهر"><input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field>
          <Field label="تلفن"><input dir="ltr" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Field label="ایمیل"><input dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="وب‌سایت"><input dir="ltr" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} /></Field>
          <div className="full"><Field label="یادداشت"><textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field></div>
        </div>
        <button className="btn btn-primary" disabled={busy}>{busy ? "…" : "ذخیره"}</button>
      </form>
    </Modal>
  );
}

// -------------------------------------------------------------- contacts
function ContactTable() {
  const { can } = useApp();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const { state, reload } = useApi(() => api.listContacts({ q: q || undefined, page, per_page: 25 }), [q, page]);

  return (
    <div>
      <div className="row-gap" style={{ marginBottom: 10 }}>
        <div className="searchbox"><input placeholder="جستجوی مخاطب…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
        {can("create") && <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>+ مخاطب جدید</button>}
      </div>
      {state.loading ? <Spinner /> : state.error ? <ErrorState text={state.error} onRetry={reload} /> : !state.data || state.data.items.length === 0
        ? <EmptyState text="مخاطبی یافت نشد." />
        : (
          <>
            <table className="tbl">
              <thead><tr><th>نام</th><th>سمت</th><th>تلفن</th><th>ایمیل</th><th>سازمان</th><th></th></tr></thead>
              <tbody>
                {state.data.items.map((c) => (
                  <ContactRow key={c.id} c={c} onDelete={async () => { await mutate(() => api.deleteContact(c.id), "حذف شد"); reload(); }} canDelete={can("delete")} />
                ))}
              </tbody>
            </table>
            <Pager page={state.data.page} pages={state.data.pages} onPage={setPage} />
          </>
        )}
      {creating && <ContactForm onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}
    </div>
  );
}

function ContactRow({ c, onDelete, canDelete }: { c: Contact; onDelete: () => void; canDelete: boolean }) {
  const orgName = useOrgName(c.organization_id);
  return (
    <tr>
      <td><b>{c.full_name}</b></td>
      <td>{c.job_title || "—"}</td>
      <td dir="ltr">{c.mobile || c.phone || "—"}</td>
      <td dir="ltr">{c.email || "—"}</td>
      <td>{c.organization_id ? <Link to={`/customers/${c.organization_id}`}>{orgName || "سازمان"}</Link> : "—"}</td>
      <td>{canDelete && <ConfirmButton onConfirm={onDelete}>حذف</ConfirmButton>}</td>
    </tr>
  );
}

function useOrgName(id: string | null): string | null {
  const { state } = useApi(() => (id ? api.getOrg(id) : Promise.resolve(null as unknown as Organization)), [id]);
  return state.data?.name ?? null;
}

function ContactForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  useState(() => { api.listOrgs({ per_page: 200 }).then((r) => setOrgs(r.items)).catch(() => undefined); return undefined; });
  const [f, setF] = useState({ first_name: "", last_name: "", job_title: "", mobile: "", email: "", organization_id: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const body: Record<string, unknown> = { first_name: f.first_name.trim(), last_name: f.last_name.trim() };
    if (f.job_title) body.job_title = f.job_title;
    if (f.mobile) body.mobile = f.mobile;
    if (f.email) body.email = f.email;
    if (f.organization_id) body.organization_id = f.organization_id;
    if (f.notes) body.notes = f.notes;
    const res = await mutate(() => api.createContact(body), "مخاطب ساخته شد ✔");
    setBusy(false);
    if (res) onSaved();
  };
  return (
    <Modal title="مخاطب جدید" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="نام *"><input required value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></Field>
          <Field label="نام خانوادگی"><input value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></Field>
          <Field label="سمت"><input value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></Field>
          <Field label="موبایل"><input dir="ltr" value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} /></Field>
          <Field label="ایمیل"><input dir="ltr" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="سازمان">
            <select value={f.organization_id} onChange={(e) => setF({ ...f, organization_id: e.target.value })}>
              <option value="">— بدون ارتباط —</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </Field>
          <div className="full"><Field label="یادداشت"><textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field></div>
        </div>
        <button className="btn btn-primary" disabled={busy}>{busy ? "…" : "ذخیره"}</button>
      </form>
    </Modal>
  );
}

export function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  if (!pages || pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>قبلی</button>
      <span className="muted small">صفحه {page} از {pages}</span>
      <button className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>بعدی</button>
    </div>
  );
}

// keep fmtDate import used (tree-shake guard for future columns)
void fmtDate;
