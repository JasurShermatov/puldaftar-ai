"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import LineChart from "./LineChart";
import { AddSheet, TxEditSheet, TxList } from "./Transactions";
import { Card, Empty, SafeRich, Segmented, Skeleton, Toast } from "./ui";
import { api, ApiError, CatTotal, Category, Dashboard, Me, Totals, Tx, TxList as TxListT } from "@/lib/api";
import { dateOf, dayLabel, MONTHS_FULL, money, monthLabel, num, pad, parseDay, short, weekLabel } from "@/lib/format";
import { confirmDialog, downloadFile, haptic, tg } from "@/lib/tg";

type Tab = "home" | "history" | "ai" | "profile";
type Period = "day" | "week" | "month" | "year";
const PERIODS: Array<[Period, string]> = [["day", "Kun"], ["week", "Hafta"], ["month", "Oy"], ["year", "Yil"]];

export default function UserApp({ me, reloadMe }: { me: Me; reloadMe: () => void }) {
  const [tab, setTab] = useState<Tab>("home");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [edit, setEdit] = useState<Tx | null>(null);
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

  return (
    <div className="app">
      <Header me={me} />
      {me.access.state === "expired" && (
        <div className="banner warn">
          ⌛️ Bepul davr tugadi. Yangi yozuvlar uchun botdagi <b>«💳 Obuna»</b> tugmasini bosing.
        </div>
      )}

      <main className="content">
        {tab === "home" && <Home dash={dash} onOpen={setEdit} />}
        {tab === "history" && <History today={dash?.today} onOpen={setEdit} version={version} />}
        {tab === "ai" && <Insights me={me} />}
        {tab === "profile" && <Profile me={me} reloadMe={reloadMe} flash={flash} />}
      </main>

      {me.access.state !== "expired" && (tab === "home" || tab === "history") && (
        <button className="fab" onClick={() => { haptic(); setAdding(true); }} aria-label="Yangi yozuv">
          +
        </button>
      )}

      <nav className="tabbar">
        {([
          ["home", "🏠", "Asosiy"],
          ["history", "📋", "Tarix"],
          ["ai", "🧠", "Tahlil"],
          ["profile", "⚙️", "Profil"],
        ] as Array<[Tab, string, string]>).map(([k, i, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => { haptic("select"); setTab(k); }}>
            <span className="ti">{i}</span>
            <span className="tl">{l}</span>
          </button>
        ))}
      </nav>

      <TxEditSheet tx={edit} categories={cats} onClose={() => setEdit(null)} onChanged={changed} />
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

function Home({ dash, onOpen }: { dash: Dashboard | null; onOpen: (t: Tx) => void }) {
  const [catPeriod, setCatPeriod] = useState<Period>("month");
  if (!dash) {
    return (
      <>
        <Skeleton h={130} />
        <Skeleton h={220} />
        <Skeleton h={220} />
      </>
    );
  }
  const t = dash.charts;
  const catList: Record<Period, CatTotal[]> = { day: dash.categories_day, week: dash.categories_week, month: dash.categories_month, year: dash.categories_year };
  const catTotals: Record<Period, Totals> = { day: dash.totals_day, week: dash.totals_week, month: dash.totals_month, year: dash.totals_year };
  const td = parseDay(dash.today);

  return (
    <>
      <section className="hero">
        <div className="hero-l">Bugungi xarajat · {dateOf(dash.today)}</div>
        <div className="hero-v">{money(dash.totals_day.expense)}</div>
        <div className="hero-s">
          {dash.totals_day.count} ta yozuv
          {dash.totals_day.income > 0 && <> · <span className="inc">+{short(dash.totals_day.income)} daromad</span></>}
          {dash.avg_daily_30 > 0 && <> · o'rtacha {short(dash.avg_daily_30)}/kun</>}
        </div>
      </section>

      <div className="kpis">
        <Kpi label="Hafta" v={dash.totals_week.expense} />
        <Kpi label={MONTHS_FULL[td.getMonth()]} v={dash.totals_month.expense} />
        <Kpi label={`${td.getFullYear()} yil`} v={dash.totals_year.expense} />
      </div>

      <ChartCard
        title="📅 Kunlik xarajat"
        sub="oxirgi 30 kun"
        total={sum(t.daily)}
        points={t.daily.map((p) => ({ label: dayLabel(p.period), full: `${dateOf(p.period)}`, value: p.expense }))}
      />
      <ChartCard
        title="🗓 Haftalik xarajat"
        sub="oxirgi 12 hafta"
        total={sum(t.weekly)}
        points={t.weekly.map((p) => ({ label: weekLabel(p.period).split("–")[0], full: `Hafta: ${weekLabel(p.period)}`, value: p.expense }))}
      />
      <ChartCard
        title="📆 Oylik xarajat"
        sub="oxirgi 12 oy"
        total={sum(t.monthly)}
        points={t.monthly.map((p) => {
          const d = parseDay(p.period);
          return { label: monthLabel(p.period), full: `${MONTHS_FULL[d.getMonth()]} ${d.getFullYear()}`, value: p.expense };
        })}
      />
      <ChartCard
        title="📊 Yillik xarajat"
        sub="yillar kesimida"
        total={sum(t.yearly)}
        points={t.yearly.map((p) => ({ label: p.period.slice(0, 4), full: `${p.period.slice(0, 4)} yil`, value: p.expense }))}
      />

      <Card title="🏷 Nimaga ketyapti" right={null}>
        <Segmented value={catPeriod} options={PERIODS} onChange={setCatPeriod} />
        <CategoryBars items={catList[catPeriod]} total={catTotals[catPeriod].expense} />
      </Card>

      <Card title="🕐 Oxirgi yozuvlar">
        <TxList items={dash.recent.slice(0, 8)} today={dash.today} onOpen={onOpen} />
      </Card>
    </>
  );
}

function sum(a: { expense: number }[]) {
  return a.reduce((s, p) => s + p.expense, 0);
}

function Kpi({ label, v }: { label: string; v: number }) {
  return (
    <div className="kpi">
      <div className="kpi-l">{label}</div>
      <div className="kpi-v">{short(v)}</div>
    </div>
  );
}

function ChartCard({ title, sub, total, points }: { title: string; sub: string; total: number; points: { label: string; full: string; value: number }[] }) {
  const nonzero = points.filter((p) => p.value > 0).length;
  const avg = nonzero ? total / points.length : 0;
  return (
    <Card
      title={
        <>
          {title} <span className="muted small">· {sub}</span>
        </>
      }
    >
      <div className="chart-meta">
        <span>
          Jami: <b>{money(total)}</b>
        </span>
        <span className="muted">o'rtacha {short(avg)}</span>
      </div>
      <LineChart points={points} />
    </Card>
  );
}

function CategoryBars({ items, total }: { items: CatTotal[]; total: number }) {
  if (!items.length) return <Empty icon="🫙" text="Bu davrda xarajat yo'q" />;
  const max = items[0]?.total || 1;
  return (
    <div className="bars">
      {items.slice(0, 10).map((c, i) => {
        const pct = total ? Math.round((100 * c.total) / total) : 0;
        return (
          <div key={`${c.id}-${i}`} className="bar-row">
            <div className="bar-top">
              <span>
                {c.emoji} {c.name || "Boshqa"} <span className="muted small">· {c.count} ta</span>
              </span>
              <span>
                <b>{num(c.total)}</b> <span className="muted small">{pct}%</span>
              </span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.max(3, (100 * c.total) / max)}%` }} />
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
            <div className="kpi">
              <div className="kpi-l">Xarajat</div>
              <div className="kpi-v exp">{short(data.totals.expense)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-l">Daromad</div>
              <div className="kpi-v inc">{short(data.totals.income)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-l">Qoldiq</div>
              <div className="kpi-v">{data.totals.net >= 0 ? "+" : "−"}{short(Math.abs(data.totals.net))}</div>
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

// ======================= AI TAHLIL =======================

type InsightResp = {
  text: string;
  stats: {
    avg_week_28: number;
    avg_day_28: number;
    last7_expense: number;
    prev7_expense: number;
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

function Profile({ me, reloadMe, flash }: { me: Me; reloadMe: () => void; flash: (m: string) => void }) {
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
    if (!(await confirmDialog("Barcha ma'lumotlaringiz butunlay o'chiriladi. Davom etasizmi?"))) return;
    if (!(await confirmDialog("Rostdan ham? Bu amalni qaytarib bo'lmaydi."))) return;
    await api.del("/api/me");
    tg()?.close();
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
          izolyatsiya (RLS) va izohlar AES-256 bilan shifrlangan. Ovozli xabarlar saqlanmaydi.
        </p>
        <button className="btn danger full" onClick={deleteAll}>
          🗑 Barcha ma'lumotlarimni o'chirish
        </button>
      </Card>
      <p className="center muted small">Hisobchi AI · v1.0</p>
    </>
  );
}
