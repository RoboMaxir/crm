import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../lib/hooks";
import { Spinner, ErrorState, EmptyState, StatCard, StatusBadge, RiskBadge } from "../components/ui";
import { fmtMoney, fmtNum, fmtDateTime, t } from "../lib/format";

export default function DashboardPage() {
  const { state } = useApi(() => api.dashboard(), []);
  if (state.loading) return <Spinner />;
  if (state.error) return <ErrorState text={state.error} />;
  const d = state.data;
  if (!d) return null;

  const s = d.sales;
  const a = d.activity;
  // opportunities closing soon: next 14 days
  const dueSoon = new Date(Date.now() + 14 * 86_400_000).toISOString();
  const closing = a.upcoming_followups.filter((x) => x.due_at && x.due_at <= dueSoon);

  return (
    <div>
      <div className="page-title">
        <div><h2>داشبورد عملیاتی</h2><p className="muted small">الان چه خبر است و چه کاری باید انجام بدهم؟</p></div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <StatCard label="سرنخ‌ها (کل)" value={fmtNum(s.total_leads)} hint={`این ماه: ${fmtNum(s.new_leads_this_month)}`} />
        <StatCard label="سرنخ راه‌یافته" value={fmtNum(s.qualified_leads)} hint={`نرخ تبدیل: ${fmtNum(s.lead_conversion_rate_pct)}٪`} tone="good" />
        <StatCard label="فرصت باز" value={fmtNum(s.open_opportunities)} hint={`ارزش خط فروش: ${fmtMoney(s.pipeline_value)}`} />
        <StatCard label="خط فروش وزنی" value={fmtMoney(s.weighted_pipeline)} hint="value × probability" />
        <StatCard label="برده این ماه" value={fmtNum(s.won_this_month.count)} hint={fmtMoney(s.won_this_month.value)} tone="good" />
        <StatCard label="باخته این ماه" value={fmtNum(s.lost_this_month.count)} hint={fmtMoney(s.lost_this_month.value)} tone="bad" />
        <StatCard label="کارهای امروز" value={fmtNum(a.counts.todays_tasks)} tone={a.counts.todays_tasks ? "warn" : undefined} />
        <StatCard label="عقب‌افتاده (Overdue)" value={fmtNum(a.counts.overdue_tasks)} tone={a.counts.overdue_tasks ? "bad" : "good"} />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3>کارهای امروز <span className="badge b-amber">{fmtNum(a.todays_tasks.length)}</span></h3>
          {a.todays_tasks.length === 0
            ? <EmptyState text="کاری برای امروز ندارید." action={<Link to="/today" className="btn btn-sm">همه کارها</Link>} />
            : a.todays_tasks.slice(0, 8).map((x) => <TaskRow key={x.id} task={x} />)}
        </div>

        <div className="card">
          <h3>عقب‌افتاده‌ها <span className="badge b-red">{fmtNum(a.overdue_tasks.length)}</span></h3>
          {a.overdue_tasks.length === 0
            ? <EmptyState text="هیچ کار عقب‌افتاده‌ای نیست. آفرین!" />
            : a.overdue_tasks.slice(0, 8).map((x) => <TaskRow key={x.id} task={x} overdue />)}
        </div>

        <div className="card">
          <h3>Next Action های نزدیک</h3>
          {closing.length === 0
            ? <EmptyState text="پیگیری نزدیکی در ۱۴ روز آینده ثبت نشده." />
            : closing.slice(0, 8).map((x) => <TaskRow key={x.id} task={x} />)}
        </div>

        <div className="card">
          <h3>بدون فعالیت (ریسک رکود)</h3>
          {a.no_activity_leads.length === 0 && a.no_activity_opportunities.length === 0
            ? <EmptyState text="همه رکوردها پیگیری فعال دارند." />
            : (
              <div className="timeline">
                {a.no_activity_leads.slice(0, 5).map((l) => (
                  <div className="tl-item" key={l.id}>
                    <span className="tl-dot" style={{ background: "#b45309" }} />
                    <div className="tl-body">
                      <Link to={`/leads?q=${encodeURIComponent(l.title)}`}>{l.title}</Link>{" "}
                      <StatusBadge status={l.status} />
                      <div className="small muted">آخرین فعالیت: {fmtDateTime(l.last_activity_at)}</div>
                    </div>
                  </div>
                ))}
                {a.no_activity_opportunities.slice(0, 5).map((o) => (
                  <div className="tl-item" key={o.id}>
                    <span className="tl-dot" style={{ background: "#b91c1c" }} />
                    <div className="tl-body">
                      <Link to={`/pipeline`}>{o.name}</Link> <RiskBadge level="high" />
                      <div className="small muted">آخرین فعالیت: {fmtDateTime(o.last_activity_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task, overdue }: { task: import("../api/types").ActivityBrief; overdue?: boolean }) {
  return (
    <div className="tl-item">
      <span className="tl-dot" style={{ background: overdue ? "#b91c1c" : "#1d4ed8" }} />
      <div className="tl-body">
        <div className="row-gap" style={{ gap: 6 }}>
          <span className="badge b-gray">{t(task.type)}</span>
          <b>{task.subject}</b>
          {task.priority && <StatusBadge status={task.priority} />}
        </div>
        <div className="small muted">
          {task.due_at ? `مهلت: ${fmtDateTime(task.due_at)}` : "بدون مهلت"}
          {overdue && <span style={{ color: "#b91c1c" }}> — عقب‌افتاده</span>}
        </div>
      </div>
    </div>
  );
}
