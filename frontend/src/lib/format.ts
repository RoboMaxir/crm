// Persian-friendly display helpers: Jalali dates via Intl, money formatting.

const faNum = new Intl.NumberFormat("fa-IR");

export function fmtMoney(v: number | null | undefined, currency = "IRR"): string {
  if (v === null || v === undefined) return "—";
  // compact for large IRR/Toman numbers
  const abs = Math.abs(v);
  let s: string;
  if (abs >= 1_000_000_000) s = `${(v / 1_000_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیارد`;
  else if (abs >= 1_000_000) s = `${(v / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیون`;
  else s = faNum.format(v);
  return `${s} ${currency === "IRR" ? "ریال" : currency}`;
}

export function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return faNum.format(v);
}

/** Jalali date+time through Intl (browser-native, no dependency). */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fa-IR", {
      calendar: "persian", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso.slice(0, 16);
  }
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fa-IR", {
      calendar: "persian", year: "numeric", month: "long", day: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso.slice(0, 10);
  }
}

export function relDays(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days <= 0) {
    const hours = Math.floor(-diffMs / 3_600_000);
    if (-diffMs > 0) return hours < 24 ? `${faNum.format(Math.max(hours,1))} ساعت دیگر` : `${faNum.format(Math.ceil(-diffMs/86_400_000))} روز دیگر`;
    return "امروز";
  }
  return `${faNum.format(days)} روز پیش`;
}

/** datetime-local input value -> ISO UTC string the backend can parse. */
export function localToIso(value: string): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

/** ISO -> value suitable for <input type="datetime-local"> (local time). */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const faLabels: Record<string, string> = {
  // org types
  customer: "مشتری", prospect: "سرنخ/احتمالی", partner: "شریک", vendor: "تأمین‌کننده", other: "سایر",
  // statuses
  active: "فعال", inactive: "غیرفعال", archived: "بایگانی",
  new: "جدید", contacted: "تماس گرفته‌شده", qualified: "راه‌یافتگی", unqualified: "نامناسب",
  converted: "تبدیل‌شده", lost: "از دست رفته", won: "برنده", open: "باز",
  pending: "در انتظار", completed: "انجام‌شده", cancelled: "لغو‌شده",
  // activity types
  call: "تماس", meeting: "جلسه", email: "ایمیل", message: "پیام", note: "یادداشت",
  task: "کار", follow_up: "پیگیری", demo: "دمو", proposal: "پیشنهاد",
  // priority
  low: "کم", medium: "متوسط", high: "زیاد", urgent: "فوری",
  // sources
  website: "وب‌سایت", referral: "معرفی", instagram: "اینستاگرام", telegram: "تلگرام",
  linkedin: "لینکدین", cold_outreach: "تماس سرد", existing_customer: "مشتری فعلی",
  partner: "شریک", event: "رویداد", manual: "دستی", unknown: "نامشخص",
  // risk levels
  none: "بدون ریسک", low: "کم", medium: "متوسط", high: "بالا", critical: "بحرانی",
  // stage names (Sales pipeline seed)
  New: "جدید", Discovery: "کشف نیاز", Qualified: "راه‌یافتگی", Proposal: "پیشنهاد",
  Negotiation: "مذاکره", Won: "برنده", Lost: "باخته",
};

export const t = (key: string | null | undefined): string =>
  (key && faLabels[key]) || key || "—";
