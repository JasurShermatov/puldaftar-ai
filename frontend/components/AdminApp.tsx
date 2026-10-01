"use client";

import { useCallback, useEffect, useState } from "react";
import LineChart from "./LineChart";
import { Card, Empty, Segmented, Sheet, Skeleton, Toast } from "./ui";
import { api, ApiError, Plan } from "@/lib/api";
import { dateOf, dayLabel, money, num, short } from "@/lib/format";
import { confirmDialog, haptic } from "@/lib/tg";

type Tab = "stats" | "users" | "payments" | "settings" | "broadcast" | "audit";

type Stats = {
  users: Record<string, number>;
  transactions: Record<string, number>;
  payments: Record<string, number>;
  reports: Record<string, number>;
  events_24h: Record<string, number>;
  daily: Array<{ day: string; tx: number; new_users: number }>;
};
type AUser = {
  id: string; telegram_id: number; username: string | null; first_name: string | null; role: string; is_blocked: boolean;
  created_at: string; last_active_at: string; tx_count: number; access: string; days_left: number; pro_until: string | null; trial_ends_at: string;
};
type Payment = {
  id: string; user_id: string; plan_code: string | null; plan_name: string | null; amount: number; days: number; status: string; note: string | null; created_at: string;
  telegram_id: number; username: string | null; first_name: string | null; approved_before: number;
};

export default function AdminApp() {
  const [tab, setTab] = useState<Tab>("stats");
  const [toast, setToast] = useState<string | null>(null);
  const flash = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2200);
  }, []);

  return (
    <div className="app">
      <header className="hdr">
        <div>
          <div className="hdr-hi">🛡 Admin panel</div>
          <div className="hdr-sub">Hisobchi AI boshqaruvi</div>
        </div>
        <a className="pill" href="/">
          ← Ilova
        </a>
      </header>
      <div className="scroll-tabs">
        {([
          ["stats", "📊 Statistika"],
          ["users", "👥 Userlar"],
          ["payments", "💳 To'lovlar"],
          ["settings", "⚙️ Sozlamalar"],
          ["broadcast", "📣 Xabar"],
          ["audit", "📜 Audit"],
        ] as Array<[Tab, string]>).map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => { haptic("select"); setTab(k); }}>
            {l}
          </button>
        ))}
      </div>
      <main className="content">
        {tab === "stats" && <StatsTab />}
        {tab === "users" && <UsersTab flash={flash} />}
        {tab === "payments" && <PaymentsTab flash={flash} />}
        {tab === "settings" && <SettingsTab flash={flash} />}
        {tab === "broadcast" && <BroadcastTab flash={flash} />}
        {tab === "audit" && <AuditTab />}
      </main>
      <Toast text={toast} />
    </div>
  );
}

function StatsTab() {
  const [s, setS] = useState<Stats | null>(null);
  const [h, setH] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    api.get<Stats>("/api/admin/stats").then(setS);
    api.get<Record<string, unknown>>("/api/admin/health").then(setH).catch(() => null);
  }, []);
  if (!s) return <Skeleton h={300} />;
  const u = s.users, p = s.payments, t = s.transactions;
  const tiles: Array<[string, string | number, string?]> = [
    ["👥 Jami userlar", num(u.users_total), `+${u.users_new_24h} bugun`],
    ["🔥 Faol (24s)", u.dau, `7 kun: ${u.wau}`],
    ["⭐️ PRO", u.pro_active],
    ["🎁 Sinovda", u.trial_active],
    ["⌛️ Tugagan", u.expired],
    ["⛔️ Bloklangan", u.blocked],
    ["🧾 Yozuvlar (24s)", t.tx_24h, `🎙 ${t.voice_24h} ovoz`],
    ["💳 Kutilmoqda", p.pending],
    ["💰 Bu oy tushum", short(p.revenue_month), `${p.approved_month} ta to'lov`],
    ["📨 Hisobot (24s)", s.reports.sent_24h, `xato 7k: ${s.reports.failed_7d}`],
  ];
  return (
    <>
      <div className="tiles">
        {tiles.map(([l, v, sub]) => (
          <div className="tile" key={l}>
            <div className="kpi-l">{l}</div>
            <div className="kpi-v">{v}</div>
            {sub && <div className="muted small">{sub}</div>}
          </div>
        ))}
      </div>
      <Card title="🧾 Kunlik yozuvlar (30 kun)">
        <LineChart labels={s.daily.map((d) => ({ label: dayLabel(d.day), full: dateOf(d.day) }))} series={[{ key: "tx", label: "Yozuvlar", color: "var(--accent)", values: s.daily.map((d) => d.tx) }]} height={150} unit="count" />
      </Card>
      <Card title="👥 Yangi userlar (30 kun)">
        <LineChart labels={s.daily.map((d) => ({ label: dayLabel(d.day), full: dateOf(d.day) }))} series={[{ key: "u", label: "Userlar", color: "var(--accent)", values: s.daily.map((d) => d.new_users) }]} height={150} unit="count" />
      </Card>
      <Card title="📈 Hodisalar (24 soat)">
        <div className="kv">
          {Object.entries(s.events_24h).map(([k, v]) => (
            <div key={k}>
              <span className="muted">{k}</span>
              <b>{v}</b>
            </div>
          ))}
        </div>
      </Card>
      {h && (
        <Card title="🩺 Tizim holati">
          <pre className="pre">{JSON.stringify(h, null, 2)}</pre>
        </Card>
      )}
    </>
  );
}

function UsersTab({ flash }: { flash: (m: string) => void }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "trial" | "pro" | "expired" | "blocked">("");
  const [data, setData] = useState<{ total: number; items: AUser[] } | null>(null);
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<AUser | null>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams({ limit: "30", offset: String(offset) });
    if (q) p.set("q", q);
    if (status) p.set("status", status);
    api.get<{ total: number; items: AUser[] }>(`/api/admin/users?${p}`).then(setData);
  }, [q, status, offset]);

  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  return (
    <>
      <input className="inp" placeholder="🔎 Telegram ID, @username yoki ism" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} />
      <div className="mt" />
      <Segmented
        value={status}
        options={[["", "Hammasi"], ["trial", "Sinov"], ["pro", "PRO"], ["expired", "Tugagan"], ["blocked", "Blok"]]}
        onChange={(v) => { setOffset(0); setStatus(v); }}
      />
      {!data ? (
        <Skeleton h={300} />
      ) : (
        <Card title={`Topildi: ${data.total}`}>
          {data.items.length === 0 && <Empty text="User topilmadi" />}
          {data.items.map((u) => (
            <button key={u.id} className="urow" onClick={() => setSel(u)}>
              <span className="u-av">{(u.first_name || u.username || "?").slice(0, 1).toUpperCase()}</span>
              <span className="tx-main">
                <span className="tx-name">
                  {u.first_name || "—"} {u.username && <span className="muted">@{u.username}</span>}
                </span>
                <span className="tx-sub">
                  ID {u.telegram_id} · {u.tx_count} yozuv · {dateOf(u.last_active_at)}
                </span>
              </span>
              <span className={`pill ${u.is_blocked ? "blocked" : u.access}`}>
                {u.is_blocked ? "⛔️" : u.role === "superadmin" ? "🛡" : u.access === "pro" ? "⭐️" : u.access === "trial" ? "🎁" : "⌛️"}
              </span>
            </button>
          ))}
          <div className="row gap mt">
            <button className="btn grow" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>
              ‹ Oldingi
            </button>
            <button className="btn grow" disabled={offset + 30 >= data.total} onClick={() => setOffset(offset + 30)}>
              Keyingi ›
            </button>
          </div>
        </Card>
      )}
      <UserSheet user={sel} onClose={() => setSel(null)} onChanged={(m) => { flash(m); load(); }} />
    </>
  );
}

function UserSheet({ user, onClose, onChanged }: { user: AUser | null; onClose: () => void; onChanged: (m: string) => void }) {
  const [detail, setDetail] = useState<{ totals: Record<string, number | string | null>; blocked_reason: string | null; payments: Payment[] } | null>(null);
  const [days, setDays] = useState("30");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    setDetail(null);
    if (user) api.get<typeof detail>(`/api/admin/users/${user.id}`).then((d) => setDetail(d));
    if (user && !plans.length) api.get<Plan[]>("/api/admin/plans").then(setPlans);
  }, [user, plans.length]);

  if (!user) return null;

  async function act(fn: () => Promise<unknown>, msg: string) {
    setBusy(true);
    try {
      await fn();
      haptic("success");
      onChanged(msg);
      onClose();
    } catch (e) {
      haptic("error");
      onChanged(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }
  const d = parseInt(days, 10) || 30;
  const isAdmin = user.role === "superadmin";

  return (
    <Sheet open={!!user} onClose={onClose} title={user.first_name || user.username || String(user.telegram_id)}>
      <div className="kv">
        <div><span className="muted">Telegram ID</span><b>{user.telegram_id}</b></div>
        <div><span className="muted">Username</span><b>{user.username ? `@${user.username}` : "—"}</b></div>
        <div><span className="muted">Holat</span><b>{user.is_blocked ? "⛔️ Bloklangan" : user.access}</b></div>
        <div><span className="muted">Ro'yxatdan o'tgan</span><b>{dateOf(user.created_at)}</b></div>
        <div><span className="muted">Oxirgi faollik</span><b>{dateOf(user.last_active_at)}</b></div>
        <div><span className="muted">Sinov tugashi</span><b>{dateOf(user.trial_ends_at)}</b></div>
        <div><span className="muted">PRO tugashi</span><b>{user.pro_until ? dateOf(user.pro_until) : "—"}</b></div>
        {detail && (
          <>
            <div><span className="muted">Yozuvlar</span><b>{String(detail.totals.tx_count)}</b></div>
            <div><span className="muted">Jami xarajat</span><b>{money(Number(detail.totals.expense_total))}</b></div>
            <div><span className="muted">Jami daromad</span><b>{money(Number(detail.totals.income_total))}</b></div>
            {detail.blocked_reason && <div><span className="muted">Blok sababi</span><b>{detail.blocked_reason}</b></div>}
          </>
        )}
      </div>
      <p className="hint">🔒 Maxfiylik: admin userning alohida yozuvlari va izohlarini ko'rmaydi — faqat umumiy summalar.</p>

      {!isAdmin && (
        <>
          <label className="lbl">Obuna ochib berish (to'lovsiz)</label>
          <div className="row gap wrap">
            {plans.filter((pl) => pl.is_active).map((pl) => (
              <button
                key={pl.code}
                className="btn primary grow"
                disabled={busy}
                onClick={async () => (await confirmDialog(`${user.first_name || user.telegram_id} uchun ${pl.name} (${pl.days} kun) PRO ochilsinmi?`)) && act(() => api.post(`/api/admin/users/${user.id}/plan`, { plan_code: pl.code }), `⭐️ ${pl.name} ochildi`)}
              >
                {pl.name}
              </button>
            ))}
          </div>
          <label className="lbl">Yoki ixtiyoriy kun</label>
          <div className="row gap">
            <input className="inp" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} style={{ maxWidth: 90 }} />
            <button className="btn grow" disabled={busy} onClick={() => act(() => api.post(`/api/admin/users/${user.id}/pro`, { days: d }), `⭐️ ${d} kun PRO berildi`)}>
              ⭐️ PRO +{d}
            </button>
            <button className="btn grow" disabled={busy} onClick={() => act(() => api.post(`/api/admin/users/${user.id}/trial`, { days: d }), `🎁 Sinov ${d} kunga uzaytirildi`)}>
              🎁 Sinov +
            </button>
          </div>
          {user.pro_until && (
            <button className="btn full mt" disabled={busy} onClick={async () => (await confirmDialog("PRO bekor qilinsinmi?")) && act(() => api.del(`/api/admin/users/${user.id}/pro`), "PRO bekor qilindi")}>
              PRO ni bekor qilish
            </button>
          )}
          <label className="lbl">Blok sababi (ixtiyoriy)</label>
          <input className="inp" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="masalan: spam" />
          <div className="row gap mt">
            {user.is_blocked ? (
              <button className="btn primary grow" disabled={busy} onClick={() => act(() => api.post(`/api/admin/users/${user.id}/block`, { blocked: false }), "✅ Blokdan chiqarildi")}>
                ✅ Blokdan chiqarish
              </button>
            ) : (
              <button className="btn warn grow" disabled={busy} onClick={() => act(() => api.post(`/api/admin/users/${user.id}/block`, { blocked: true, reason: reason || null }), "⛔️ Bloklandi")}>
                ⛔️ Bloklash
              </button>
            )}
            <button
              className="btn danger grow"
              disabled={busy}
              onClick={async () => (await confirmDialog("User va uning BARCHA ma'lumotlari o'chirilsinmi?")) && act(() => api.del(`/api/admin/users/${user.id}`), "🗑 O'chirildi")}
            >
              🗑 O'chirish
            </button>
          </div>
        </>
      )}
      {detail && detail.payments.length > 0 && (
        <>
          <label className="lbl">To'lovlar tarixi</label>
          {detail.payments.map((p) => (
            <div key={p.id} className="kvline">
              <span>{dateOf(p.created_at)}</span>
              <span>{money(p.amount)}</span>
              <span className={`pill ${p.status}`}>{p.status}</span>
            </div>
          ))}
        </>
      )}
    </Sheet>
  );
}

function PaymentsTab({ flash }: { flash: (m: string) => void }) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected" | "all">("pending");
  const [items, setItems] = useState<Payment[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    setItems(null);
    api.get<Payment[]>(`/api/admin/payments?status=${status}`).then(setItems);
  }, [status]);
  useEffect(load, [load]);

  async function decide(p: Payment, ok: boolean) {
    const who = p.username ? `@${p.username}` : p.first_name || p.telegram_id;
    const q = ok
      ? `${who} uchun ${money(p.amount)} to'lov TASDIQLANSINMI? (${p.days} kun PRO)\nBank ilovasida pul kelganini tekshirdingizmi?`
      : `${who} arizasi rad etilsinmi?`;
    if (!(await confirmDialog(q))) return;
    setBusy(p.id);
    try {
      if (ok) await api.post(`/api/admin/payments/${p.id}/approve`);
      else await api.post(`/api/admin/payments/${p.id}/reject`, { reason: "Chek tasdiqlanmadi" });
      haptic("success");
      flash(ok ? "✅ Tasdiqlandi, PRO yoqildi" : "❌ Rad etildi");
      load();
    } catch (e) {
      flash(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Segmented value={status} options={[["pending", "Kutilmoqda"], ["approved", "Tasdiqlangan"], ["rejected", "Rad etilgan"], ["all", "Hammasi"]]} onChange={setStatus} />
      <p className="hint">Chekni user sizga Telegramda yuboradi. Pul bank ilovangizga kelganini tekshirib, keyin tasdiqlang.</p>
      {!items ? (
        <Skeleton h={200} />
      ) : items.length === 0 ? (
        <Empty icon="✅" text="Ro'yxat bo'sh" />
      ) : (
        items.map((p) => (
          <Card key={p.id}>
            <div className="pay">
              <div>
                <div className="tx-name">
                  {p.first_name || "—"} {p.username && <span className="muted">@{p.username}</span>}
                </div>
                <div className="tx-sub">
                  ID {p.telegram_id} · {dateOf(p.created_at)} {p.created_at.slice(11, 16)} UTC
                  {p.approved_before > 0 && ` · avval ${p.approved_before} marta to'lagan`}
                </div>
              </div>
              <div className="right">
                <div className="plan-p">{money(p.amount)}</div>
                <div className="muted small">{p.plan_name || "PRO"} · {p.days} kun</div>
              </div>
            </div>
            {p.status === "pending" ? (
              <div className="row gap mt">
                <button className="btn danger grow" disabled={busy === p.id} onClick={() => decide(p, false)}>
                  ❌ Rad etish
                </button>
                <button className="btn primary grow" disabled={busy === p.id} onClick={() => decide(p, true)}>
                  ✅ Tasdiqlash
                </button>
              </div>
            ) : (
              <div className="mt">
                <span className={`pill ${p.status}`}>{p.status === "approved" ? "✅ Tasdiqlangan" : "❌ Rad etilgan"}</span>
                {p.note && <span className="muted small"> · {p.note}</span>}
              </div>
            )}
          </Card>
        ))
      )}
    </>
  );
}

type SettingsResp = {
  billing: { trial_days: number; card_number: string; card_holder: string; admin_username: string };
  ai: { auto_save_threshold: number; confirm_threshold: number };
};

function SettingsTab({ flash }: { flash: (m: string) => void }) {
  const [s, setS] = useState<SettingsResp | null>(null);
  useEffect(() => {
    api.get<SettingsResp>("/api/admin/settings").then(setS);
  }, []);
  if (!s) return <Skeleton h={300} />;

  const b = s.billing;
  const setB = (k: keyof SettingsResp["billing"], v: string | number) => setS({ ...s, billing: { ...b, [k]: v } });
  const setA = (k: keyof SettingsResp["ai"], v: number) => setS({ ...s, ai: { ...s.ai, [k]: v } });

  async function saveBilling() {
    try {
      await api.patch("/api/admin/settings/billing", {
        trial_days: Number(b.trial_days),
        card_number: b.card_number, card_holder: b.card_holder, admin_username: b.admin_username,
      });
      haptic("success");
      flash("✅ Saqlandi");
    } catch (e) {
      flash((e as Error).message);
    }
  }
  async function saveAI() {
    try {
      await api.patch("/api/admin/settings/ai", s!.ai);
      flash("✅ Saqlandi");
    } catch (e) {
      flash((e as Error).message);
    }
  }

  return (
    <>
      <PlansEditor flash={flash} />
      <Card title="💳 To'lov rekvizitlari">
        <label className="lbl">Bepul sinov (kun)</label>
        <input className="inp" inputMode="numeric" value={b.trial_days} onChange={(e) => setB("trial_days", e.target.value.replace(/\D/g, ""))} />
        <label className="lbl">Karta raqami</label>
        <input className="inp" inputMode="numeric" maxLength={23} placeholder="8600 0000 0000 0000" value={b.card_number}
          onChange={(e) => setB("card_number", e.target.value.replace(/\D/g, "").slice(0, 19).replace(/(\d{4})(?=\d)/g, "$1 "))} />
        <p className="hint">Yangi karta darhol botdagi to'lov oynasida ko'rinadi.</p>
        <label className="lbl">Karta egasi</label>
        <input className="inp" placeholder="Ism Familiya" value={b.card_holder} onChange={(e) => setB("card_holder", e.target.value)} />
        <label className="lbl">Chek yuboriladigan admin (@username)</label>
        <input className="inp" placeholder="@admin" value={b.admin_username} onChange={(e) => setB("admin_username", e.target.value)} />
        <button className="btn primary full mt" onClick={saveBilling}>
          Saqlash
        </button>
      </Card>
      <Card title="🧠 AI aniqlik chegaralari">
        <label className="lbl">Avto-saqlash (≥): {s.ai.auto_save_threshold}</label>
        <input type="range" min={0.6} max={0.99} step={0.01} value={s.ai.auto_save_threshold} onChange={(e) => setA("auto_save_threshold", Number(e.target.value))} className="range" />
        <label className="lbl">Tasdiq so'rash (≥): {s.ai.confirm_threshold}</label>
        <input type="range" min={0.3} max={0.9} step={0.01} value={s.ai.confirm_threshold} onChange={(e) => setA("confirm_threshold", Number(e.target.value))} className="range" />
        <p className="hint">Undan past bo'lsa bot saqlamaydi va aniqlashtiruvchi savol beradi.</p>
        <button className="btn primary full mt" onClick={saveAI}>
          Saqlash
        </button>
      </Card>
    </>
  );
}

function PlansEditor({ flash }: { flash: (m: string) => void }) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  useEffect(() => {
    api.get<Plan[]>("/api/admin/plans").then(setPlans);
  }, []);
  if (!plans) return <Skeleton h={200} />;

  const set = (i: number, k: keyof Plan, v: unknown) => setPlans(plans.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  const reload = () => api.get<Plan[]>("/api/admin/plans").then(setPlans);

  async function remove(p: Plan) {
    if (!(await confirmDialog(`«${p.name}» tarifi o'chirilsinmi?`))) return;
    try {
      const r = await api.del<{ result: string }>(`/api/admin/plans/${p.code}`);
      haptic("success");
      flash(r.result === "archived" ? "🗄 To'lovlar tarixida bor — arxivlandi (userlarga ko'rinmaydi)" : "🗑 O'chirildi");
      reload();
    } catch (e) {
      flash(e instanceof ApiError ? e.message : "Xatolik");
    }
  }

  async function save(p: Plan) {
    try {
      await api.patch(`/api/admin/plans/${p.code}`, {
        name: p.name, days: Number(p.days), price: Number(p.price),
        old_price: p.old_price ? Number(p.old_price) : 0, badge: p.badge || "", is_active: p.is_active,
      });
      haptic("success");
      flash(`✅ ${p.name} saqlandi`);
    } catch (e) {
      flash((e as Error).message);
    }
  }

  return (
    <Card title="📦 Tariflar">
      <p className="hint" style={{ marginTop: 0 }}>
        Chegirma qilish uchun «Eski narx» ga oldingi narxni yozing — botda ustidan chizilgan holda ko'rinadi. Belgi: masalan «🔥 -30%».
      </p>
      {plans.map((p, i) => (
        <div key={p.code} className="plan-edit">
          <div className="row gap">
            <input className="inp grow" value={p.name} onChange={(e) => set(i, "name", e.target.value)} />
            <button className={`switch ${p.is_active ? "on" : ""}`} onClick={() => set(i, "is_active", !p.is_active)} aria-pressed={!!p.is_active} title="Faol">
              <span />
            </button>
          </div>
          <div className="row gap">
            <div className="grow">
              <label className="lbl">Narx (so'm)</label>
              <input className="inp" inputMode="numeric" value={p.price} onChange={(e) => set(i, "price", e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="grow">
              <label className="lbl">Eski narx</label>
              <input className="inp" inputMode="numeric" placeholder="—" value={p.old_price ?? ""} onChange={(e) => set(i, "old_price", e.target.value.replace(/\D/g, "") || null)} />
            </div>
          </div>
          <div className="row gap">
            <div className="grow">
              <label className="lbl">Kun</label>
              <input className="inp" inputMode="numeric" value={p.days} onChange={(e) => set(i, "days", e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="grow">
              <label className="lbl">Belgi</label>
              <input className="inp" maxLength={24} placeholder="🔥 -30%" value={p.badge ?? ""} onChange={(e) => set(i, "badge", e.target.value)} />
            </div>
          </div>
          <div className="row gap mt">
            <button className="btn danger" onClick={() => remove(p)}>
              🗑
            </button>
            <button className="btn primary grow" onClick={() => save(p)}>
              Saqlash
            </button>
          </div>
        </div>
      ))}
      <NewPlan onCreated={(m) => { flash(m); reload(); }} />
    </Card>
  );
}

type Seg = "all" | "trial" | "expired" | "pro" | "active7" | "inactive7";
type BcRow = { id: number; segment: string; kind: string; preview: string | null; total: number; sent: number; failed: number; status: string; created_at: string };

const SEG_OPTS: Array<[Seg, string]> = [["all", "Hammaga"], ["trial", "Sinovda"], ["expired", "Tugagan"], ["pro", "PRO"], ["active7", "Faol"], ["inactive7", "Nofaol"]];

/** Rasmni brauzerda kichraytirib (max 1600px, JPEG) base64 ga o'giradi — tez yuklanadi. */
function fileToJpegBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, 1600 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.87));
    };
    img.onerror = reject;
    img.src = url;
  });
}

function NewPlan({ onCreated }: { onCreated: (m: string) => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", days: "30", price: "", old_price: "", badge: "" });
  const [busy, setBusy] = useState(false);
  const digits = (v: string) => v.replace(/\D/g, "");

  async function create() {
    if (!f.name.trim() || !Number(f.price) || !Number(f.days)) return;
    setBusy(true);
    try {
      await api.post("/api/admin/plans", {
        name: f.name.trim(), days: Number(f.days), price: Number(f.price),
        old_price: f.old_price ? Number(f.old_price) : null, badge: f.badge || null,
      });
      haptic("success");
      setF({ name: "", days: "30", price: "", old_price: "", badge: "" });
      setOpen(false);
      onCreated("✅ Yangi tarif qo'shildi");
    } catch (e) {
      onCreated(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="btn full mt" onClick={() => setOpen(true)}>
        ➕ Yangi tarif qo'shish
      </button>
    );
  }
  return (
    <div className="plan-edit">
      <label className="lbl">Nomi</label>
      <input className="inp" maxLength={40} placeholder="masalan: 6 oylik" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <div className="row gap">
        <div className="grow">
          <label className="lbl">Narx (so'm)</label>
          <input className="inp" inputMode="numeric" value={f.price} onChange={(e) => setF({ ...f, price: digits(e.target.value) })} />
        </div>
        <div className="grow">
          <label className="lbl">Kun</label>
          <input className="inp" inputMode="numeric" value={f.days} onChange={(e) => setF({ ...f, days: digits(e.target.value) })} />
        </div>
      </div>
      <div className="row gap">
        <div className="grow">
          <label className="lbl">Eski narx</label>
          <input className="inp" inputMode="numeric" placeholder="—" value={f.old_price} onChange={(e) => setF({ ...f, old_price: digits(e.target.value) })} />
        </div>
        <div className="grow">
          <label className="lbl">Belgi</label>
          <input className="inp" maxLength={24} placeholder="🔥 -30%" value={f.badge} onChange={(e) => setF({ ...f, badge: e.target.value })} />
        </div>
      </div>
      <div className="row gap mt">
        <button className="btn" onClick={() => setOpen(false)}>Bekor</button>
        <button className="btn primary grow" onClick={create} disabled={busy || !f.name.trim() || !f.price || !f.days}>
          Qo'shish
        </button>
      </div>
    </div>
  );
}

function BroadcastTab({ flash }: { flash: (m: string) => void }) {
  const [text, setText] = useState("");
  const [seg, setSeg] = useState<Seg>("all");
  const [count, setCount] = useState<number | null>(null);
  const [btnText, setBtnText] = useState("");
  const [btnUrl, setBtnUrl] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [hist, setHist] = useState<BcRow[]>([]);

  const loadHist = useCallback(() => {
    api.get<BcRow[]>("/api/admin/broadcasts").then(setHist).catch(() => null);
  }, []);
  useEffect(() => {
    api.get<Plan[]>("/api/admin/plans").then(setPlans).catch(() => null);
    loadHist();
  }, [loadHist]);
  useEffect(() => {
    setCount(null);
    api.get<{ count: number }>(`/api/admin/broadcast/count?segment=${seg}`).then((r) => setCount(r.count)).catch(() => null);
  }, [seg]);

  const pm = (code: string) => plans.find((p) => p.code === code);
  const priceTxt = (code: string) => {
    const p = pm(code);
    if (!p) return "";
    return p.old_price && p.old_price > p.price ? `<s>${money(p.old_price)}</s> → <b>${money(p.price)}</b>` : `<b>${money(p.price)}</b>`;
  };
  const templates: Array<[string, string]> = [
    ["🔥 1 oylik chegirma", `🔥 <b>CHEGIRMA!</b>\n\n${pm("m1")?.name || "1 oylik"} PRO obuna endi atigi ${priceTxt("m1")}!\n\n✅ Ovoz bilan xarajat yozish\n✅ Har kungi hisobot va AI tahlil\n✅ Excel yuklab olish\n\nBotdagi «💳 Obuna» tugmasini bosing 👇`],
    ["🎁 3 oylik taklif", `🎁 <b>Maxsus taklif</b>\n\n${pm("m3")?.name || "3 oylik"} PRO — ${priceTxt("m3")}\nUzoqroq muddat — arzonroq narx!\n\n«💳 Obuna» tugmasini bosing 👇`],
    ["💎 1 yillik chegirma", `💎 <b>Yillik obunada katta chegirma!</b>\n\n${pm("y1")?.name || "1 yillik"} PRO — ${priceTxt("y1")}\nButun yil xarajatlaringiz nazoratda 📊\n\n«💳 Obuna» tugmasini bosing 👇`],
    ["📣 Yangilik", `📣 <b>Yangilik!</b>\n\n`],
  ];

  async function pickPhoto(f: File | undefined) {
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) return flash("Faqat JPG/PNG rasm");
    try {
      setPhoto(await fileToJpegBase64(f));
    } catch {
      flash("Rasmni o'qib bo'lmadi");
    }
  }

  async function send(target: Seg | "self") {
    if (!text.trim() && !photo) return;
    if (target !== "self" && !(await confirmDialog(`Xabar ${count ?? "?"} ta userga yuborilsinmi?`))) return;
    setBusy(true);
    try {
      const r = await api.post<{ queued: number }>("/api/admin/broadcast", {
        text, segment: target,
        button_text: btnText.trim() || null, button_url: btnUrl.trim() || null,
        photo_base64: photo,
      });
      haptic("success");
      if (target === "self") flash("🧪 Test xabar sizga yuborildi — botni tekshiring");
      else {
        flash(`📣 ${r.queued} ta userga yuborilmoqda`);
        setText("");
        setPhoto(null);
        setBtnText("");
        setBtnUrl("");
        setTimeout(loadHist, 1500);
      }
    } catch (e) {
      haptic("error");
      flash(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card title="📣 Ommaviy xabar (reklama, chegirma)">
        <label className="lbl" style={{ marginTop: 0 }}>Kimlarga</label>
        <Segmented value={seg} options={SEG_OPTS} onChange={setSeg} />
        <p className="hint">👥 Qabul qiluvchilar: <b>{count ?? "…"}</b> ta (bloklanganlar hisobga olinmaydi)</p>

        <label className="lbl">Tayyor shablonlar</label>
        <div className="chips">
          {templates.map(([l, t]) => (
            <button key={l} className="chip" onClick={() => setText(t)}>
              {l}
            </button>
          ))}
        </div>

        <label className="lbl">Matn</label>
        <textarea className="inp area" rows={7} maxLength={photo ? 1024 : 3500} value={text} onChange={(e) => setText(e.target.value)} placeholder="Xabar matni. Formatlash: <b>qalin</b>, <i>qiya</i>, <s>chizilgan</s>" />
        <div className="muted small right">{text.length} / {photo ? 1024 : 3500}</div>

        <label className="lbl">Rasm (ixtiyoriy)</label>
        {photo ? (
          <div className="bc-photo">
            <img src={photo} alt="" />
            <button className="btn small danger" onClick={() => setPhoto(null)}>✕ Olib tashlash</button>
          </div>
        ) : (
          <input className="inp" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => pickPhoto(e.target.files?.[0])} />
        )}

        <label className="lbl">Tugma (ixtiyoriy)</label>
        <div className="row gap">
          <input className="inp" style={{ maxWidth: "40%" }} maxLength={40} placeholder="Batafsil" value={btnText} onChange={(e) => setBtnText(e.target.value)} />
          <input className="inp grow" placeholder="https://t.me/..." value={btnUrl} onChange={(e) => setBtnUrl(e.target.value)} />
        </div>

        <div className="row gap mt">
          <button className="btn grow" onClick={() => send("self")} disabled={busy || (!text.trim() && !photo)}>
            🧪 O'zimga test
          </button>
          <button className="btn primary grow" onClick={() => send(seg)} disabled={busy || (!text.trim() && !photo)}>
            🚀 Yuborish
          </button>
        </div>
        <p className="hint">
          💡 Video yoki tayyor postni yubormoqchimisiz? Botga <b>/broadcast</b> yozing va postni yuboring — u aynan shunday nusxalanadi.
          Yuborish fonda (~20 ta/sek) bo'ladi, tugagach botda hisobot keladi.
        </p>
      </Card>

      <Card title="🕘 Yuborilganlar" right={<button className="btn small" onClick={loadHist}>↻</button>}>
        {!hist.length && <Empty text="Hali ommaviy xabar yuborilmagan" />}
        {hist.map((h) => (
          <div key={h.id} className="audit">
            <div className="row gap">
              <b className="grow">{(h.preview || "").replace(/<[^>]+>/g, "").slice(0, 60) || "—"}</b>
              <span className={`pill ${h.status === "done" ? "approved" : "pending"}`}>{h.status === "done" ? "✅" : "⏳"}</span>
            </div>
            <div className="muted small">
              {dateOf(h.created_at)} {h.created_at.slice(11, 16)} UTC · {h.segment} · {h.kind} · ✅ {h.sent} / {h.total}
              {h.failed ? ` · ❌ ${h.failed}` : ""}
            </div>
          </div>
        ))}
      </Card>
    </>
  );
}

function AuditTab() {
  const [rows, setRows] = useState<Array<{ id: number; actor_tg_id: number; action: string; target_tg_id: number | null; target_username: string | null; meta: Record<string, unknown>; created_at: string }> | null>(null);
  useEffect(() => {
    api.get<typeof rows>("/api/admin/audit?limit=200").then(setRows);
  }, []);
  if (!rows) return <Skeleton h={300} />;
  if (!rows.length) return <Empty text="Hali amallar yo'q" />;
  return (
    <Card title="📜 Admin amallari jurnali">
      {rows.map((r) => (
        <div key={r.id} className="audit">
          <div>
            <b>{r.action}</b> <span className="muted small">· admin {r.actor_tg_id}</span>
          </div>
          <div className="muted small">
            {dateOf(r.created_at)} {r.created_at.slice(11, 16)} UTC
            {r.target_tg_id ? ` · user ${r.target_username ? "@" + r.target_username : r.target_tg_id}` : ""}
            {Object.keys(r.meta || {}).length ? ` · ${JSON.stringify(r.meta)}` : ""}
          </div>
        </div>
      ))}
    </Card>
  );
}
