"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Chat from "./Chat";
import { DebtRow, DebtSheet, DebtsTab } from "./Debts";
import LineChart, { Series } from "./LineChart";
import { AddSheet, TxEditSheet, TxList } from "./Transactions";
import { Card, Empty, SafeRich, Segmented, Skeleton, Toast } from "./ui";
import { api, ApiError, Category, CatTotal, Dashboard, Debt, Me, SeriesPoint, Totals, Tx, TxList as TxListT } from "@/lib/api";
import { dateOf, dayLabel, MONTHS_FULL, money, monthLabel, num, pad, parseDay, short, weekLabel } from "@/lib/format";
import { confirmDialog, downloadFile, haptic, tg } from "@/lib/tg";

type Tab = "home" | "history" | "debts" | "ai" | "profile";
type Period = "day" | "week" | "month" | "year";
type Flow = "expense" | "income" | "both";
const PERIODS: Array<[Period, string]> = [["day", "Kun"], ["week", "Hafta"], ["month", "Oy"], ["year", "Yil"]];
const TABS: Array<[Tab, string, string]> = [
  ["home", "🏠", "Asosiy"],
  ["history", "📋", "Tarix"],
  ["debts", "🤝", "Qarzlar"],
  ["ai", "💬", "AI"],
  ["profile", "⚙️", "Profil"],
];
const EXP_COLOR = "var(--expense)";
const INC_COLOR = "var(--income)";

function initialTab(): Tab {
  if (typeof window === "undefined") return "home";
  const t = new URLSearchParams(window.location.search).get("tab");
  return (TABS.some(([k]) => k === t) ? t : "home") as Tab;
}

export default function UserApp({ me, reloadMe }: { me: Me; reloadMe: () => void }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [edit, setEdit] = useState<Tx | null>(null);
  const [debtOpen, setDebtOpen] = useState<Debt | null>(null);
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const flash = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2200);
  }, []);

  const load = useCallback(async () => {
    const [d, c] = await Promise.all([api.get<Dashboard>("/api/dashboard"), api.get<Category[]>("/api/categories")]);
    setDash(d);
    setCats(c);
  }, []);

  useEffect(() => {
    load().catch(() => flash("Ma'lumotni yuklab bo'lmadi"));
  }, [load, flash, version]);

  const changed = (m: string) => {
    flash(m);
    setVersion((v) => v + 1);
  };
  const canAdd = me.access.state !== "expired";

  return (
    <div className="app">
      <Header me={me} />
      {me.access.state === "expired" && (
        <div className="banner warn">
          ⌛️ Bepul davr tugadi. Yangi yozuvlar uchun botdagi <b>«💳 Obuna»</b> tugmasini bosing.
        </div>
      )}

      <main className={`content ${tab === "ai" ? "content-chat" : ""}`}>
        {tab === "home" && <Home dash={dash} onOpen={setEdit} onOpenDebt={setDebtOpen} goDebts={() => setTab("debts")} />}
        {tab === "history" && <History today={dash?.today} onOpen={setEdit} version={version} />}
        {tab === "debts" && <DebtsTab version={version} onChanged={changed} canAdd={canAdd} />}
        {tab === "ai" && <AiTab me={me} />}
        {tab === "profile" && <Profile me={me} reloadMe={reloadMe} flash={flash} onWiped={() => { setVersion((v) => v + 1); setTab("home"); }} />}
      </main>

      {canAdd && (tab === "home" || tab === "history") && (
        <button className="fab" onClick={() => { haptic(); setAdding(true); }} aria-label="Yangi yozuv">
          +
        </button>
      )}

      <nav className="tabbar">
        {TABS.map(([k, i, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => { haptic("select"); setTab(k); }}>
            <span className="ti">{i}</span>
            <span className="tl">{l}</span>
          </button>
        ))}
      </nav>

      <TxEditSheet tx={edit} categories={cats} onClose={() => setEdit(null)} onChanged={changed} />
      <DebtSheet debt={debtOpen} onClose={() => setDebtOpen(null)} onChanged={(m) => { setDebtOpen(null); changed(m); }} />
      <AddSheet open={adding} onClose={() => setAdding(false)} categories={cats} onDone={changed} />
      <Toast text={toast} />
    </div>
  );
}

function Header({ me }: { me: Me }) {
  const name = me.user.first_name || "Do'st";
  const badge =
    me.access.state === "pro" ? (me.is_admin ? "🛡 Admin" : `⭐️ PRO · ${me.access.days_left} kun`) :
    me.access.state === "trial" ? `🎁 Sinov · ${me.access.days_left} kun` : "⌛️ Tugagan";
  return (
    <header className="hdr">
      <div>
        <div className="hdr-hi">Salom, {name} 👋</div>
        <div className="hdr-sub">Hisobchi AI</div>
      </div>
      <div className="row gap">
        {me.is_admin && (
          <a className="pill" href="/admin/">
            🛡 Admin
          </a>
        )}
        <span className={`pill ${me.access.state}`}>{badge}</span>
      </div>
    </header>
  );
}

// ======================= ASOSIY =======================

function Home({ dash, onOpen, onOpenDebt, goDebts }: { dash: Dashboard | null; onOpen: (t: Tx) => void; onOpenDebt: (d: Debt) => void; goDebts: () => void }) {
  const [catPeriod, setCatPeriod] = useState<Period>("month");
  const [catFlow, setCatFlow] = useState<"expense" | "income">("expense");
  const [flow, setFlow] = useState<Flow>("both");
  if (!dash) {
    return (
      <>
        <Skeleton h={150} />
        <Skeleton h={70} />
        <Skeleton h={240} />
        <Skeleton h={240} />
      </>
    );
  }
  const t = dash.charts;
  const expCats: Record<Period, CatTotal[]> = { day: dash.categories_day, week: dash.categories_week, month: dash.categories_month, year: dash.categories_year };
  const incCats: Record<Period, CatTotal[]> = { day: dash.income_categories_day, week: dash.income_categories_week, month: dash.income_categories_month, year: dash.income_categories_year };
  const totals: Record<Period, Totals> = { day: dash.totals_day, week: dash.totals_week, month: dash.totals_month, year: dash.totals_year };
  const td = parseDay(dash.today);
  const d = dash.totals_day;
  const m = dash.totals_month;
  const debts = dash.debts;

  return (
    <>
      <section className="hero">
        <div className="hero-l">Bugun · {dateOf(dash.today)}</div>
        <div className="hero-grid">
          <div>
            <div className="hero-k">💸 Xarajat</div>
            <div className="hero-n">{money(d.expense)}</div>
          </div>
          <div>
            <div className="hero-k">💰 Daromad</div>
            <div className="hero-n inc">{d.income ? `+${money(d.income)}` : "—"}</div>
          </div>
        </div>
        <div className="hero-s">
          {d.count} ta yozuv
          {dash.avg_daily_30 > 0 && <> · o'rtacha {short(dash.avg_daily_30)}/kun</>}
          {d.income > 0 && <> · qoldiq <b>{d.net >= 0 ? "+" : "−"}{short(Math.abs(d.net))}</b></>}
        </div>
      </section>

      <div className="kpis">
        <Kpi label="Hafta" t={dash.totals_week} />
        <Kpi label={MONTHS_FULL[td.getMonth()]} t={dash.totals_month} />
        <Kpi label={`${td.getFullYear()} yil`} t={dash.totals_year} />
      </div>

      <Card className="netcard">
        <div className="net-row">
          <div>
            <div className="kpi-l">{MONTHS_FULL[td.getMonth()]}: sof natija</div>
            <div className={`net-v ${m.net >= 0 ? "pos" : "neg"}`}>
              {m.net >= 0 ? "+" : "−"}{money(Math.abs(m.net))}
            </div>
          </div>
          <div className="net-bar" aria-hidden>
            <span className="exp" style={{ width: `${pct(m.expense, m.expense + m.income)}%` }} />
            <span className="inc" style={{ width: `${pct(m.income, m.expense + m.income)}%` }} />
          </div>
        </div>
        <div className="net-legend">
          <span><i style={{ background: EXP_COLOR }} /> Xarajat {short(m.expense)}</span>
          <span><i style={{ background: INC_COLOR }} /> Daromad {short(m.income)}</span>
        </div>
      </Card>

      <div className="row gap wrap between">
        <h3 className="sec-title">📈 Dinamika</h3>
        <Segmented value={flow} options={[["both", "Ikkalasi"], ["expense", "Xarajat"], ["income", "Daromad"]]} onChange={setFlow} />
      </div>
      <div className="charts">
        <ChartCard title="📅 Kunlik" sub="oxirgi 30 kun" flow={flow} points={t.daily} labelOf={(p) => ({ label: dayLabel(p.period), full: dateOf(p.period) })} />
        <ChartCard title="🗓 Haftalik" sub="oxirgi 12 hafta" flow={flow} points={t.weekly} labelOf={(p) => ({ label: weekLabel(p.period).split("–")[0], full: `Hafta: ${weekLabel(p.period)}` })} />
        <ChartCard
          title="📆 Oylik"
          sub="oxirgi 12 oy"
          flow={flow}
          points={t.monthly}
          labelOf={(p) => {
            const x = parseDay(p.period);
            return { label: monthLabel(p.period), full: `${MONTHS_FULL[x.getMonth()]} ${x.getFullYear()}` };
          }}
        />
        <ChartCard title="📊 Yillik" sub="yillar kesimida" flow={flow} points={t.yearly} labelOf={(p) => ({ label: p.period.slice(0, 4), full: `${p.period.slice(0, 4)} yil` })} />
      </div>

      <Card
        title={catFlow === "expense" ? "🏷 Nimaga ketyapti" : "🏷 Nimadan kelyapti"}
        right={
          <div className="seg mini">
            <button className={catFlow === "expense" ? "on" : ""} onClick={() => { haptic("select"); setCatFlow("expense"); }}>Xarajat</button>
            <button className={catFlow === "income" ? "on" : ""} onClick={() => { haptic("select"); setCatFlow("income"); }}>Daromad</button>
          </div>
        }
      >
        <Segmented value={catPeriod} options={PERIODS} onChange={setCatPeriod} />
        <CategoryBars
          items={catFlow === "expense" ? expCats[catPeriod] : incCats[catPeriod]}
          total={catFlow === "expense" ? totals[catPeriod].expense : totals[catPeriod].income}
          color={catFlow === "expense" ? EXP_COLOR : INC_COLOR}
          emptyText={catFlow === "expense" ? "Bu davrda xarajat yo'q" : "Bu davrda daromad yo'q"}
        />
      </Card>

      {(debts.open_count > 0 || debts.items.length > 0) && (
        <Card
          title="🤝 Qarzlar"
          right={
            <button className="btn small" onClick={goDebts}>
              Hammasi ›
            </button>
          }
        >
          <div className="kpis two">
            <div className="kpi">
              <div className="kpi-l">➡️ Sizga qaytarishadi</div>
              <div className="kpi-v inc">{short(debts.given_open)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-l">⬅️ Siz qaytarasiz</div>
              <div className="kpi-v exp">{short(debts.taken_open)}</div>
            </div>
          </div>
          {debts.overdue_count > 0 && <p className="hint err">⚠️ {debts.overdue_count} ta qarz muddati o'tgan</p>}
          <div className="debts mt">
            {debts.items.slice(0, 4).map((x) => (
              <DebtRow key={x.id} d={x} onOpen={onOpenDebt} />
            ))}
          </div>
        </Card>
      )}

      <Card title="🕐 Oxirgi yozuvlar">
        <TxList items={dash.recent.slice(0, 8)} today={dash.today} onOpen={onOpen} />
      </Card>
    </>
  );
}

function pct(a: number, total: number) {
  return total ? Math.max(0, Math.min(100, Math.round((100 * a) / total))) : 0;
}

function Kpi({ label, t }: { label: string; t: Totals }) {
  return (
    <div className="kpi">
      <div className="kpi-l">{label}</div>
      <div className="kpi-v">{short(t.expense)}</div>
      <div className={`kpi-s ${t.income ? "inc" : "muted"}`}>{t.income ? `+${short(t.income)}` : "daromad yo'q"}</div>
    </div>
  );
}

function ChartCard({ title, sub, points, flow, labelOf }: { title: string; sub: string; points: SeriesPoint[]; flow: Flow; labelOf: (p: SeriesPoint) => { label: string; full: string } }) {
  const labels = useMemo(() => points.map(labelOf), [points, labelOf]);
  const series = useMemo(() => {
    const out: Series[] = [];
    if (flow !== "income") out.push({ key: "e", label: "Xarajat", color: EXP_COLOR, values: points.map((p) => p.expense) });
    if (flow !== "expense") out.push({ key: "i", label: "Daromad", color: INC_COLOR, values: points.map((p) => p.income) });
    return out;
  }, [points, flow]);
  const exp = points.reduce((s, p) => s + p.expense, 0);
  const inc = points.reduce((s, p) => s + p.income, 0);
  const n = Math.max(1, points.length);
  return (
    <Card
      title={
        <>
          {title} <span className="muted small">· {sub}</span>
        </>
      }
    >
      <div className="chart-meta">
        {flow !== "income" && (
          <span className="legend">
            <i style={{ background: EXP_COLOR }} /> Xarajat <b>{short(exp)}</b> <span className="muted">· o'rt. {short(exp / n)}</span>
          </span>
        )}
        {flow !== "expense" && (
          <span className="legend">
            <i style={{ background: INC_COLOR }} /> Daromad <b>{short(inc)}</b> <span className="muted">· o'rt. {short(inc / n)}</span>
          </span>
        )}
      </div>
      <LineChart labels={labels} series={series} />
    </Card>
  );
}

function CategoryBars({ items, total, color, emptyText }: { items: CatTotal[]; total: number; color: string; emptyText: string }) {
  if (!items.length) return <Empty icon="🫙" text={emptyText} />;
  const max = items[0]?.total || 1;
  return (
    <div className="bars">
      {items.slice(0, 10).map((c, i) => {
        const p = total ? Math.round((100 * c.total) / total) : 0;
        return (
          <div key={`${c.id}-${i}`} className="bar-row">
            <div className="bar-top">
              <span>
                {c.emoji} {c.name || "Boshqa"} <span className="muted small">· {c.count} ta</span>
              </span>
              <span>
                <b>{num(c.total)}</b> <span className="muted small">{p}%</span>
              </span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.max(3, (100 * c.total) / max)}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ======================= TARIX =======================

function shiftDate(d: string, period: Period, dir: number): string {
  const x = parseDay(d);
  if (period === "day") x.setDate(x.getDate() + dir);
  if (period === "week") x.setDate(x.getDate() + 7 * dir);
  if (period === "month") x.setMonth(x.getMonth() + dir, 1);
  if (period === "year") x.setFullYear(x.getFullYear() + dir, 0, 1);
  return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`;
}

function periodTitle(data: TxListT | null, period: Period) {
  if (!data) return "…";
  const s = parseDay(data.start);
  if (period === "day") return dateOf(data.start);
  if (period === "week") return `${dateOf(data.start)} – ${dateOf(data.end)}`;
  if (period === "month") return `${MONTHS_FULL[s.getMonth()]} ${s.getFullYear()}`;
  return `${s.getFullYear()} yil`;
}

function History({ today, onOpen, version }: { today?: string; onOpen: (t: Tx) => void; version: number }) {
  const [period, setPeriod] = useState<Period>("month");
  const [date, setDate] = useState<string | null>(null);
  const [type, setType] = useState<"all" | "expense" | "income">("all");
  const [data, setData] = useState<TxListT | null>(null);
  const base = date || today || "";

  useEffect(() => {
    if (!base) return;
    setData(null);
    const q = new URLSearchParams({ period, date: base, limit: "500" });
    if (type !== "all") q.set("type", type);
    api.get<TxListT>(`/api/transactions?${q}`).then(setData).catch(() => setData(null));
  }, [period, base, type, version]);

  const isFuture = useMemo(() => (today ? shiftDate(base, period, 1) > today && period === "day" : false), [base, period, today]);

  return (
    <>
      <Segmented value={period} options={PERIODS} onChange={(p) => { setPeriod(p); }} />
      <div className="datenav">
        <button className="icon-btn" onClick={() => setDate(shiftDate(base, period, -1))} aria-label="Oldingi">
          ‹
        </button>
        <div className="datenav-t">{periodTitle(data, period)}</div>
        <button className="icon-btn" disabled={isFuture} onClick={() => setDate(shiftDate(base, period, 1))} aria-label="Keyingi">
          ›
        </button>
      </div>
      {data ? (
        <>
          <div className="kpis">
            <button className={`kpi tap ${type === "expense" ? "sel" : ""}`} onClick={() => setType(type === "expense" ? "all" : "expense")}>
              <div className="kpi-l">Xarajat</div>
              <div className="kpi-v exp">{short(data.totals.expense)}</div>
            </button>
            <button className={`kpi tap ${type === "income" ? "sel" : ""}`} onClick={() => setType(type === "income" ? "all" : "income")}>
              <div className="kpi-l">Daromad</div>
              <div className="kpi-v inc">{short(data.totals.income)}</div>
            </button>
            <div className="kpi">
              <div className="kpi-l">Qoldiq</div>
              <div className={`kpi-v ${data.totals.net >= 0 ? "inc" : "exp"}`}>{data.totals.net >= 0 ? "+" : "−"}{short(Math.abs(data.totals.net))}</div>
            </div>
          </div>
          <Segmented value={type} options={[["all", "Hammasi"], ["expense", "Xarajat"], ["income", "Daromad"]]} onChange={setType} />
          <Card>
            <TxList items={data.items} today={today || ""} onOpen={onOpen} />
          </Card>
        </>
      ) : (
        <Skeleton h={300} />
      )}
    </>
  );
}

// ======================= AI =======================

function AiTab({ me }: { me: Me }) {
  const [mode, setMode] = useState<"chat" | "insight">("chat");
  return (
    <>
      <Segmented value={mode} options={[["chat", "💬 Suhbat"], ["insight", "📊 Tahlil"]]} onChange={setMode} />
      {mode === "chat" ? <Chat canAsk={me.access.state !== "expired"} /> : <Insights me={me} />}
    </>
  );
}

type InsightResp = {
  text: string;
  stats: {
    avg_week_28: number;
    avg_day_28: number;
    last7_expense: number;
    prev7_expense: number;
    last7_income: number;
    change_7_pct: number | null;
    top_weekday: string | null;
    categories_28: Array<{ name: string; total: number; avg_week: number; share_pct: number; count: number }>;
  };
};

function Insights({ me }: { me: Me }) {
  const [kind, setKind] = useState<"daily" | "weekly">("weekly");
  const [data, setData] = useState<InsightResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setErr(null);
      try {
        setData(await api.get<InsightResp>(`/api/insights?kind=${kind}${refresh ? "&refresh=true" : ""}`));
      } catch (e) {
        setErr(e instanceof ApiError && e.status === 402 ? "AI tahlil PRO foydalanuvchilar uchun." : "Tahlilni yuklab bo'lmadi");
      } finally {
        setLoading(false);
      }
    },
    [kind],
  );

  useEffect(() => {
    load();
  }, [load]);

  const s = data?.stats;
  return (
    <>
      <Segmented value={kind} options={[["daily", "📅 Bugungi"], ["weekly", "🗓 Haftalik chuqur"]]} onChange={setKind} />
      <Card
        title="🧠 AI maslahatchi"
        right={
          <button className="btn small" onClick={() => load(true)} disabled={loading}>
            {loading ? "…" : "↻ Yangilash"}
          </button>
        }
      >
        {err ? <p className="muted">{err}</p> : data ? <SafeRich html={data.text} /> : <Skeleton h={120} />}
        {!me.ai_enabled && <p className="hint">ℹ️ OpenAI kaliti ulanmagan — oddiy statistik tahlil ko'rsatilmoqda.</p>}
      </Card>
      {s && (
        <>
          <div className="kpis">
            <div className="kpi">
              <div className="kpi-l">O'rtacha/hafta</div>
              <div className="kpi-v">{short(s.avg_week_28)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-l">O'rtacha/kun</div>
              <div className="kpi-v">{short(s.avg_day_28)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-l">7 kun o'zgarish</div>
              <div className={`kpi-v ${s.change_7_pct != null && s.change_7_pct > 0 ? "exp" : "inc"}`}>
                {s.change_7_pct == null ? "—" : `${s.change_7_pct > 0 ? "+" : ""}${s.change_7_pct}%`}
              </div>
            </div>
          </div>
          <Card title="📌 Oxirgi 4 hafta: haftasiga o'rtacha">
            {s.categories_28.length ? (
              <div className="bars">
                {s.categories_28.map((c) => (
                  <div key={c.name} className="bar-row">
                    <div className="bar-top">
                      <span>{c.name}</span>
                      <span>
                        <b>{short(c.avg_week)}</b>
                        <span className="muted small">/hafta · {c.share_pct}%</span>
                      </span>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${Math.max(3, c.share_pct)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty text="Hali ma'lumot yetarli emas" />
            )}
            {s.top_weekday && <p className="hint">📅 Eng ko'p xarajat qilinadigan kun: <b>{s.top_weekday}</b></p>}
          </Card>
        </>
      )}
    </>
  );
}

// ======================= PROFIL =======================

function Profile({ me, reloadMe, flash, onWiped }: { me: Me; reloadMe: () => void; flash: (m: string) => void; onWiped: () => void }) {
  const [period, setPeriod] = useState<Period>("month");
  const [fmt, setFmt] = useState<"xlsx" | "csv">("xlsx");
  const [busy, setBusy] = useState(false);

  async function exportTo(delivery: "chat" | "link") {
    setBusy(true);
    try {
      if (delivery === "chat") {
        await api.post("/api/export", { period, format: fmt, delivery });
        haptic("success");
        flash("📥 Fayl bot chatiga yuborildi");
      } else {
        const r = await api.post<{ url: string }>("/api/export", { period, format: fmt, delivery });
        downloadFile(r.url, `hisobchi_${period}.${fmt}`);
      }
    } catch (e) {
      flash(e instanceof ApiError && e.status === 402 ? "Yuklab olish PRO uchun" : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function setSetting(patch: Record<string, unknown>) {
    await api.patch("/api/me/settings", patch);
    haptic("success");
    flash("✅ Saqlandi");
    reloadMe();
  }

  async function deleteAll() {
    const what = me.is_admin
      ? "Barcha ma'lumotlaringiz (xarajat, daromad, qarzlar, AI suhbat) o'chiriladi. Superadmin akkaunti qoladi. Davom etasizmi?"
      : "Barcha ma'lumotlaringiz va akkauntingiz butunlay o'chiriladi. Davom etasizmi?";
    if (!(await confirmDialog(what))) return;
    if (!(await confirmDialog("Rostdan ham? Bu amalni qaytarib bo'lmaydi."))) return;
    setBusy(true);
    try {
      const r = await api.del<{ ok: boolean; mode: "data" | "account" }>("/api/me");
      haptic("success");
      if (r.mode === "data") {
        flash("🗑 Barcha ma'lumotlar o'chirildi");
        reloadMe();
        onWiped();
      } else {
        tg()?.close();
      }
    } catch (e) {
      haptic("error");
      flash(e instanceof ApiError ? e.message : "O'chirib bo'lmadi, qaytadan urinib ko'ring");
    } finally {
      setBusy(false);
    }
  }

  const endStr = me.access.ends_at ? dateOf(me.access.ends_at) : "—";

  async function payInBot() {
    setBusy(true);
    try {
      await api.post("/api/billing/plans-to-chat");
      tg()?.close();
    } catch {
      flash("Botdagi «💳 Obuna» tugmasini bosing");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card title="💳 Obuna">
        <div className="plan mb">
          <div>
            <div className="plan-s">
              {me.access.state === "pro" ? "⭐️ PRO" : me.access.state === "trial" ? "🎁 Bepul sinov" : "⌛️ Muddati tugagan"}
            </div>
            {me.access.state !== "expired" && !me.is_admin && <div className="muted small">{endStr} gacha · {me.access.days_left} kun qoldi</div>}
          </div>
        </div>
        <div className="plans">
          {me.plans.map((p) => (
            <div key={p.code} className="plan-card">
              <div className="plan-left">
                <div>
                  <b>{p.name}</b> {p.badge && <span className="pill trial">{p.badge}</span>}
                </div>
                <div className="muted small">
                  {p.days} kun{p.days > 31 ? ` · oyiga ~${short(Math.round((p.price * 30) / p.days))}` : ""}
                </div>
              </div>
              <div className="right">
                <div className="plan-price">{money(p.price)}</div>
                {p.old_price && p.old_price > p.price && <s className="muted small">{money(p.old_price)}</s>}
              </div>
            </div>
          ))}
        </div>
        {!me.is_admin && (
          <button className="btn primary full mt" onClick={payInBot} disabled={busy}>
            💳 Botda to'lash
          </button>
        )}
        <p className="hint">Tarifni tanlaysiz → karta raqami chiqadi → to'lab, chekni adminga yuborasiz → admin tasdiqlagach PRO yoqiladi.</p>
      </Card>

      <Card title="📥 Yuklab olish (Excel / CSV)">
        <Segmented value={period} options={[["day", "Kunlik"], ["week", "Haftalik"], ["month", "Oylik"], ["year", "Yillik"]]} onChange={setPeriod} />
        <div className="mt" />
        <Segmented value={fmt} options={[["xlsx", "Excel (.xlsx)"], ["csv", "CSV"]]} onChange={setFmt} />
        <div className="row gap mt">
          <button className="btn grow" onClick={() => exportTo("link")} disabled={busy}>
            ⬇️ Yuklab olish
          </button>
          <button className="btn primary grow" onClick={() => exportTo("chat")} disabled={busy}>
            💬 Chatga yuborish
          </button>
        </div>
        <p className="hint">Excel faylda: xulosa, tranzaksiyalar, kategoriyalar, dinamika va qarzlar varaqlari.</p>
      </Card>

      <Card title="🕛 Kunlik hisobot">
        <div className="setting">
          <span>Har kuni hisobot yuborish</span>
          <button className={`switch ${me.user.report_enabled ? "on" : ""}`} onClick={() => setSetting({ report_enabled: !me.user.report_enabled })} aria-pressed={me.user.report_enabled}>
            <span />
          </button>
        </div>
        <div className="setting">
          <span>Vaqti</span>
          <select className="inp sel" value={me.user.report_time} onChange={(e) => setSetting({ report_time: e.target.value })}>
            {["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "23:30", "23:59"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="setting">
          <span>Vaqt zonasi</span>
          <select className="inp sel" value={me.user.timezone} onChange={(e) => setSetting({ timezone: e.target.value })}>
            {[["Asia/Tashkent", "Toshkent (UTC+5)"], ["Asia/Samarkand", "Samarqand (UTC+5)"], ["Asia/Almaty", "Almaty (UTC+5)"], ["Europe/Moscow", "Moskva (UTC+3)"], ["Asia/Dubai", "Dubay (UTC+4)"], ["Europe/Istanbul", "Istanbul (UTC+3)"]].map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </Card>

      <Card title="🔒 Maxfiylik">
        <p className="hint">
          Ma'lumotlaringiz faqat sizga ko'rinadi: har bir so'rov Telegram imzosi bilan tekshiriladi, bazada qator darajasida
          izolyatsiya (RLS), izohlar, qarz ismlari va AI suhbat AES-256 bilan shifrlangan. Ovozli xabarlar saqlanmaydi.
        </p>
        <button className="btn danger full" onClick={deleteAll} disabled={busy}>
          🗑 Barcha ma'lumotlarimni o'chirish
        </button>
        {me.is_admin && <p className="hint">Superadmin akkaunti o'chirilmaydi (.env SUPERADMIN_IDS) — faqat ma'lumotlar tozalanadi.</p>}
      </Card>
      <p className="center muted small">Hisobchi AI · v1.1</p>
    </>
  );
}
