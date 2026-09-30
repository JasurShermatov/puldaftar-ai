import { initData } from "./tg";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Authorization: `tma ${initData()}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : msg;
    } catch {
      /* noop */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  patch: <T,>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {}),
  del: <T,>(p: string) => request<T>("DELETE", p),
};

// ---------- Tiplar ----------
export type Totals = { expense: number; income: number; net: number; count: number };
export type SeriesPoint = { period: string; expense: number; income: number; count: number };
export type CatTotal = { id: number | null; key: string | null; name: string | null; emoji: string | null; total: number; count: number };
export type Tx = {
  id: string;
  type: "expense" | "income";
  amount: number;
  currency: string;
  category_id: number | null;
  category_key: string | null;
  category_name: string | null;
  category_emoji: string | null;
  description: string;
  occurred_at: string;
  source: string;
};
export type Category = { id: number; user_id: string | null; type: "expense" | "income"; key: string; name: string; emoji: string; is_active: boolean };

export type Me = {
  user: { first_name: string | null; username: string | null; language: string; timezone: string; report_enabled: boolean; report_time: string; created_at: string };
  access: { state: "trial" | "pro" | "expired"; ends_at: string | null; days_left: number };
  plans: Plan[];
  is_admin: boolean;
  ai_enabled: boolean;
};

export type Plan = { code: string; name: string; days: number; price: number; old_price: number | null; badge: string | null; is_active?: boolean; sort?: number };

export type Dashboard = {
  today: string;
  totals_day: Totals;
  totals_week: Totals;
  totals_month: Totals;
  totals_year: Totals;
  charts: { daily: SeriesPoint[]; weekly: SeriesPoint[]; monthly: SeriesPoint[]; yearly: SeriesPoint[] };
  categories_day: CatTotal[];
  categories_week: CatTotal[];
  categories_month: CatTotal[];
  categories_year: CatTotal[];
  recent: Tx[];
  avg_daily_30: number;
  avg_weekly_12: number;
};

export type TxList = { period: string; start: string; end: string; totals: Totals; categories: CatTotal[]; items: Tx[] };

export type IngestResult = {
  kind: "saved" | "pending" | "clarify" | "expired" | "duplicate" | "empty";
  saved: Tx[];
  pending_id: string | null;
  pending_items: Array<{ type: string; amount: number; category_name: string; category_emoji: string; description: string }>;
  question: string | null;
  amount_options: number[];
};
