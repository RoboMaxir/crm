// API types — mirror of the FastAPI /api/v1 contract (verified against routers).

export interface Identity {
  user_id: string;
  tenant_id: string;
  role: "admin" | "manager" | "sales" | "member";
  full_name: string;
  permissions: string[]; // view|create|update|delete|assign|export|manage
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ActivityBrief {
  id: string;
  type: string;
  subject: string;
  due_at: string | null;
  assigned_to: string | null;
  status: string;
  priority?: string;
}

export interface RiskInfo {
  stale?: boolean;
  overdue?: boolean;
  aging_days?: number;
  no_next_action?: boolean;
  risk_score?: number;
  risk_level?: string;
  flags?: string[];
}

export interface Organization {
  id: string;
  tenant_id: string;
  name: string;
  legal_name: string | null;
  type: string; // customer|prospect|partner|vendor|other
  industry: string | null;
  website: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  country: string | null;
  source: string | null;
  owner_id: string | null;
  status: string; // active|inactive|archived
  notes: string | null;
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface Contact {
  id: string;
  tenant_id: string;
  organization_id: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  job_title: string | null;
  department: string | null;
  phone: string | null;
  mobile: string | null;
  email: string | null;
  linkedin: string | null;
  owner_id: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface Lead {
  id: string;
  tenant_id: string;
  title: string;
  organization_id: string | null;
  contact_id: string | null;
  source: string | null;
  status: string; // new|contacted|qualified|unqualified|converted|lost
  qualification: string;
  score: number;
  estimated_value: number;
  currency: string;
  owner_id: string | null;
  expected_close_date: string | null;
  last_activity_at: string | null;
  next_activity_at: string | null;
  converted_at: string | null;
  lost_reason: string | null;
  notes: string | null;
  converted_organization_id: string | null;
  converted_opportunity_id: string | null;
  created_at: string;
  updated_at: string;
  next_action: ActivityBrief | null;
  last_activity: ActivityBrief | null;
  risk: RiskInfo;
  tags?: string[];
}

export interface Pipeline {
  id: string;
  tenant_id: string;
  name: string;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Stage {
  id: string;
  tenant_id: string;
  pipeline_id: string;
  name: string;
  order: number;
  probability: number;
  color: string;
  is_won: boolean;
  is_lost: boolean;
}

export interface Opportunity {
  id: string;
  tenant_id: string;
  name: string;
  organization_id: string;
  primary_contact_id: string | null;
  lead_id: string | null;
  pipeline_id: string;
  stage_id: string;
  owner_id: string | null;
  value: number;
  currency: string;
  probability: number;
  weighted_value: number;
  expected_close_date: string | null;
  status: string; // open|won|lost
  lost_reason: string | null;
  source: string | null;
  description: string | null;
  last_activity_at: string | null;
  next_activity_at: string | null;
  stage_entered_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  stage_name: string | null;
  stage_color: string | null;
  organization_name: string | null;
  days_in_stage: number | null;
  next_action: ActivityBrief | null;
  last_activity: ActivityBrief | null;
  risk: RiskInfo;
  tags?: string[];
}

export interface Activity {
  id: string;
  tenant_id: string;
  type: string; // call|meeting|email|message|note|task|follow_up|demo|proposal|other
  subject: string;
  description: string | null;
  organization_id: string | null;
  contact_id: string | null;
  lead_id: string | null;
  opportunity_id: string | null;
  assigned_to: string | null;
  status: string; // pending|completed|cancelled
  priority: string; // low|medium|high|urgent
  due_at: string | null;
  completed_at: string | null;
  occurred_at: string | null;
  created_by: string | null;
  overdue_notified?: boolean;
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface ConvertResult {
  lead: Lead;
  organization: Organization;
  contact: Contact | null;
  opportunity: Opportunity;
}

export interface QuickCaptureResult {
  organization: Organization;
  organization_created: boolean;
  contact: Contact | null;
  contact_created: boolean;
  lead: Lead;
  next_action: Activity | null;
}

export interface DashboardSales {
  total_leads: number;
  new_leads_this_month: number;
  qualified_leads: number;
  lead_conversion_rate_pct: number;
  open_opportunities: number;
  pipeline_value: number;
  weighted_pipeline: number;
  won_this_month: { count: number; value: number };
  lost_this_month: { count: number; value: number };
  win_rate_month_pct: number;
  revenue_won_alltime: number;
  customers_count: number;
  organizations_count: number;
}

export interface DashboardActivity {
  todays_tasks: ActivityBrief[];
  overdue_tasks: ActivityBrief[];
  upcoming_followups: ActivityBrief[];
  no_activity_leads: Array<{ id: string; title: string; status: string; owner_id: string | null; last_activity_at: string | null }>;
  no_activity_opportunities: Array<{ id: string; name: string; organization_id: string; owner_id: string | null; last_activity_at: string | null }>;
  counts: { todays_tasks: number; overdue_tasks: number; no_activity_leads: number; no_activity_opportunities: number };
}

export interface DashboardFull {
  sales: DashboardSales;
  activity: DashboardActivity;
}

export interface KanbanCard {
  id: string;
  name: string;
  organization_name: string | null;
  value: number;
  probability: number;
  weighted_value: number;
  currency: string;
  owner_id: string | null;
  expected_close_date: string | null;
  next_action: ActivityBrief | null;
  days_in_stage: number | null;
  risk_level: string;
  risk_flags: string[];
}

export interface KanbanStage {
  stage: { id: string; name: string; order: number; color: string; probability: number };
  count: number;
  value: number;
  cards: KanbanCard[];
}

export interface PipelineBoard {
  pipeline: { id: string; name: string };
  stages: KanbanStage[];
  totals: { value: number; weighted: number };
}

export interface SearchResults {
  organizations: Array<Pick<Organization, "id" | "name" | "type" | "status" | "city">>;
  contacts: Array<{ id: string; full_name: string; email: string | null; job_title: string | null; organization_id: string | null }>;
  leads: Array<{ id: string; title: string; status: string; score: number; owner_id: string | null; organization_id: string | null }>;
  opportunities: Array<{ id: string; name: string; status: string; value: number; weighted_value: number; organization_id: string; stage_id: string; owner_id: string | null }>;
  activities: Array<{ id: string; type: string; subject: string; status: string; due_at: string | null; organization_id: string | null; lead_id: string | null; opportunity_id: string | null }>;
  total: number;
}

export interface Customer360 {
  identity: Organization;
  tags: string[];
  contacts: Contact[];
  commercial: {
    leads: Array<Pick<Lead, "id" | "title" | "status" | "score" | "estimated_value"> & Record<string, unknown>>;
    opportunities: Array<Partial<Opportunity> & { stage_name?: string | null }>;
    won_deals: number;
    lost_deals: number;
    open_deals: number;
    revenue_won: number;
    pipeline_value: number;
    weighted_pipeline: number;
  };
  relationship: {
    last_touch_at: string | null;
    days_since_last_touch: number | null;
    interaction_count: number;
    channels: string[];
    relationship_days: number | null;
    risk_flags: string[];
  };
  timeline: Activity[];
  tasks: { open: Activity[]; overdue: Activity[]; today: Activity[]; upcoming: Activity[] };
  next_actions: ActivityBrief[];
  notes: Array<{ id: string; subject: string; description: string | null; created_at: string }>;
  events: Array<{ event: string; entity: string; entity_id: string; occurred_at: string; payload: Record<string, unknown> }>;
  intelligence: Array<Record<string, unknown>>;
}

export interface Enums {
  organization_types: string[];
  lead_statuses: string[];
  lead_qualifications: string[];
  lead_sources: string[];
  lead_lost_reasons: string[];
  opportunity_statuses: string[];
  [k: string]: string[];
}

export interface ApiErrorBody {
  error?: string;
  detail?: string | Array<{ msg?: string; loc?: unknown[] }>;
}
