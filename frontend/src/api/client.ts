// Central API client — every request goes through here.
// Base URL, Bearer auth, JSON handling and typed error mapping are centralized.

import type { ApiErrorBody } from "./types";

const KEY_STORAGE = "crm_api_key";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

// Human-readable Persian messages per HTTP status; backend domain messages
// ({"error","detail"}) always take precedence when present.
export function friendlyError(err: ApiError): string {
  const base = err.message && err.message !== err.code ? err.message : "";
  switch (err.status) {
    case 400: return base || "درخواست نامعتبر است.";
    case 401: return "کلید API نامعتبر است یا منقضی شده. دوباره وارد شوید.";
    case 403: return base || "نقش شما اجازه انجام این عملیات را ندارد.";
    case 404: return base || "رکورد مورد نظر یافت نشد.";
    case 409: return base || "این عملیات ممکن نیست (تعارض وضعیت).";
    case 422: return base || "داده‌های ارسالی کامل/صحیح نیست.";
    default:
      if (err.status >= 500) return "خطای سرور. لطفاً بعداً دوباره تلاش کنید.";
      return base || `خطای غیرمنتظره (${err.status}).`;
  }
}

export const auth = {
  get apiKey(): string | null {
    return sessionStorage.getItem(KEY_STORAGE);
  },
  set(key: string) {
    sessionStorage.setItem(KEY_STORAGE, key.trim());
  },
  clear() {
    sessionStorage.removeItem(KEY_STORAGE);
  },
};

const BASE = "/api/v1";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  const key = auth.apiKey;
  if (key) headers["Authorization"] = `Bearer ${key}`;

  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, { ...opts, headers });
  } catch {
    throw new ApiError(0, "network", "اتصال به سرور برقرار نشد. آیا backend در حال اجرا است؟");
  }

  if (resp.status === 204) return undefined as T;

  let body: unknown = null;
  const text = await resp.text();
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }

  if (!resp.ok) {
    const b = (body || {}) as ApiErrorBody & { detail?: unknown };
    let detail = typeof b.detail === "string" ? b.detail : "";
    if (Array.isArray(b.detail)) {
      // FastAPI validation errors
      detail = b.detail
        .map((e: { msg?: string; loc?: unknown[] }) =>
          `${(e.loc || []).slice(1).join(".")} — ${e.msg ?? ""}`.trim())
        .join(" | ");
    }
    throw new ApiError(resp.status, b.error || `http_${resp.status}`, detail);
  }
  return body as T;
}

const qs = (params: Record<string, unknown>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
};

// ------------------------------------------------------------------ endpoints
export const api = {
  me: () => request<import("./types").Identity>("/me"),

  // organizations / customers
  listOrgs: (p: Record<string, unknown> = {}) =>
    request<import("./types").Page<import("./types").Organization>>(`/organizations${qs(p)}`),
  getOrg: (id: string) => request<import("./types").Organization>(`/organizations/${id}`),
  createOrg: (data: object) =>
    request<import("./types").Organization>("/organizations", { method: "POST", body: JSON.stringify(data) }),
  updateOrg: (id: string, data: object) =>
    request<import("./types").Organization>(`/organizations/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteOrg: (id: string) => request<void>(`/organizations/${id}`, { method: "DELETE" }),
  customer360: (id: string) => request<import("./types").Customer360>(`/organizations/${id}/360`),
  setOrgTags: (id: string, tags: string[]) =>
    request<{ tags: string[] }>(`/organizations/${id}/tags`, { method: "PUT", body: JSON.stringify(tags) }),

  // contacts
  listContacts: (p: Record<string, unknown> = {}) =>
    request<import("./types").Page<import("./types").Contact>>(`/contacts${qs(p)}`),
  createContact: (data: object) =>
    request<import("./types").Contact>("/contacts", { method: "POST", body: JSON.stringify(data) }),
  updateContact: (id: string, data: object) =>
    request<import("./types").Contact>(`/contacts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteContact: (id: string) => request<void>(`/contacts/${id}`, { method: "DELETE" }),

  // leads
  listLeads: (p: Record<string, unknown> = {}) =>
    request<import("./types").Page<import("./types").Lead>>(`/leads${qs(p)}`),
  getLead: (id: string) => request<import("./types").Lead>(`/leads/${id}`),
  createLead: (data: object) =>
    request<import("./types").Lead>("/leads", { method: "POST", body: JSON.stringify(data) }),
  updateLead: (id: string, data: object) =>
    request<import("./types").Lead>(`/leads/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  convertLead: (id: string, data: object = {}) =>
    request<import("./types").ConvertResult>(`/leads/${id}/convert`, { method: "POST", body: JSON.stringify(data) }),
  loseLead: (id: string, lost_reason: string) =>
    request<import("./types").Lead>(`/leads/${id}/lose`, { method: "POST", body: JSON.stringify({ lost_reason }) }),

  // opportunities
  listOpps: (p: Record<string, unknown> = {}) =>
    request<import("./types").Page<import("./types").Opportunity>>(`/opportunities${qs(p)}`),
  getOpp: (id: string) => request<import("./types").Opportunity>(`/opportunities/${id}`),
  createOpp: (data: object) =>
    request<import("./types").Opportunity>("/opportunities", { method: "POST", body: JSON.stringify(data) }),
  updateOpp: (id: string, data: object) =>
    request<import("./types").Opportunity>(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  moveStage: (id: string, stage_id: string, extra: object = {}) =>
    request<import("./types").Opportunity>(`/opportunities/${id}/move-stage`, {
      method: "POST", body: JSON.stringify({ stage_id, ...extra }),
    }),
  reopenOpp: (id: string, stage_id: string) =>
    request<import("./types").Opportunity>(`/opportunities/${id}/reopen`, {
      method: "POST", body: JSON.stringify({ stage_id }),
    }),

  // pipelines
  listPipelines: () => request<import("./types").Pipeline[]>("/pipelines"),
  ensureDefaultPipeline: () => request<import("./types").Pipeline[]>("/pipelines/ensure-default", { method: "POST", body: "{}" }),
  stages: (pid: string) => request<import("./types").Stage[]>(`/pipelines/${pid}/stages`),

  // activities
  listActivities: (p: Record<string, unknown> = {}) =>
    request<import("./types").Page<import("./types").Activity>>(`/activities${qs(p)}`),
  createActivity: (data: object) =>
    request<import("./types").Activity>("/activities", { method: "POST", body: JSON.stringify(data) }),
  updateActivity: (id: string, data: object) =>
    request<import("./types").Activity>(`/activities/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  completeActivity: (id: string) =>
    request<import("./types").Activity>(`/activities/${id}/complete`, { method: "POST", body: "{}" }),
  cancelActivity: (id: string) =>
    request<import("./types").Activity>(`/activities/${id}/cancel`, { method: "POST", body: "{}" }),
  sweepOverdue: () => request<{ marked: number }>("/activities/sweep-overdue", { method: "POST", body: "{}" }),

  // dashboards
  dashboard: () => request<import("./types").DashboardFull>("/dashboard"),
  ceoDashboard: () => request<Record<string, unknown>>("/dashboard/ceo"),
  pipelineBoard: (pipeline_id?: string) =>
    request<import("./types").PipelineBoard>(`/dashboard/pipeline${pipeline_id ? `?pipeline_id=${pipeline_id}` : ""}`),

  // search / quick capture / settings
  search: (q: string) => request<import("./types").SearchResults>(`/search${qs({ q })}`),
  quickCapture: (data: object) =>
    request<import("./types").QuickCaptureResult>("/quick/capture", { method: "POST", body: JSON.stringify(data) }),
  enums: () => request<import("./types").Enums>("/settings/enums"),
};
