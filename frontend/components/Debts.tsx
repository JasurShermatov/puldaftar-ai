"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Debt, DebtList } from "@/lib/api";
import { dateOf, money, num, short, todayISO } from "@/lib/format";
import { confirmDialog, haptic } from "@/lib/tg";
import { Card, Empty, Segmented, Sheet, Skeleton } from "./ui";

/** Muddat belgisi: ok (yashil) · soon (sariq) · overdue (qizil) · none */
export function dueTone(d: Debt): "ok" | "soon" | "overdue" | "none" {
  if (d.status === "paid") return "none";
  if (d.days_left == null) return "none";
  if (d.days_left < 0) return "overdue";
  if (d.days_left <= 3) return "soon";
  return "ok";
}

export function dueText(d: Debt): string {
  if (d.status === "paid") return d.paid_at ? `yopildi ${dateOf(d.paid_at)}` : "yopilgan";
  if (!d.due_at || d.days_left == null) return "muddatsiz";
  const ds = dateOf(d.due_at).slice(0, 5);
  if (d.days_left < 0) return `${ds} · ${Math.abs(d.days_left)} kun o'tdi`;
  if (d.days_left === 0) return `${ds} · bugun`;
  if (d.days_left === 1) return `${ds} · ertaga`;
  return `${ds} · ${d.days_left} kun`;
}

export function DebtRow({ d, onOpen }: { d: Debt; onOpen: (d: Debt) => void }) {
  const tone = dueTone(d);
  const pct = d.amount ? Math.round((100 * d.paid_amount) / d.amount) : 0;
  return (
    <button className="debt" onClick={() => onOpen(d)}>
      <span className={`debt-ic ${d.direction}`}>{d.direction === "given" ? "➡️" : "⬅️"}</span>
      <span className="debt-main">
        <span className="debt-name">
          {d.counterparty || (d.direction === "given" ? "Kimgadir" : "Kimdandir")}
          {d.note ? <span className="muted small"> · {d.note}</span> : null}
        </span>
        <span className={`debt-due ${tone}`}>
          {tone === "overdue" ? "⚠️ " : tone === "soon" ? "⏰ " : "📅 "}
          {dueText(d)}
        </span>
        {d.paid_amount > 0 && d.status === "open" && (
          <span className="debt-prog">
            <span style={{ width: `${pct}%` }} />
          </span>
        )}
      </span>
      <span className={`debt-amt ${d.direction} ${d.status}`}>
        {d.status === "paid" ? num(d.amount) : num(d.remaining)}
        {d.paid_amount > 0 && d.status === "open" && <span className="muted small"> / {num(d.amount)}</span>}
      </span>
    </button>
  );
}

export function DebtsTab({ version, onChanged, canAdd }: { version: number; onChanged: (m: string) => void; canAdd: boolean }) {
  const [status, setStatus] = useState<"open" | "paid">("open");
  const [data, setData] = useState<DebtList | null>(null);
  const [open, setOpen] = useState<Debt | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setData(await api.get<DebtList>(`/api/debts?status=${status}`));
  }, [status]);

  useEffect(() => {
    setData(null);
    load().catch(() => setData({ items: [], summary: { given_open: 0, taken_open: 0, open_count: 0, overdue_count: 0, due_soon_count: 0, next_due: null } }));
  }, [load, version]);

  const s = data?.summary;
  const given = data?.items.filter((d) => d.direction === "given") || [];
  const taken = data?.items.filter((d) => d.direction === "taken") || [];

  return (
    <>
      <section className="hero debts">
        <div className="hero-l">🤝 Qarzlar</div>
        <div className="hero-grid">
          <div>
            <div className="hero-k">Sizga qaytarishadi</div>
            <div className="hero-n">{s ? short(s.given_open) : "…"}</div>
          </div>
          <div>
            <div className="hero-k">Siz qaytarasiz</div>
            <div className="hero-n">{s ? short(s.taken_open) : "…"}</div>
          </div>
        </div>
        <div className="hero-s">
          {s && s.open_count ? `${s.open_count} ta ochiq` : "Ochiq qarz yo'q"}
          {s && s.overdue_count > 0 && <> · <span className="warn-t">⚠️ {s.overdue_count} ta muddati o'tgan</span></>}
          {s && !s.overdue_count && s.due_soon_count > 0 && <> · ⏰ {s.due_soon_count} ta muddati yaqin</>}
        </div>
      </section>

      <div className="row gap">
        <div className="grow">
          <Segmented value={status} options={[["open", "Ochiq"], ["paid", "Yopilgan"]]} onChange={setStatus} />
        </div>
        {canAdd && (
          <button className="btn primary" onClick={() => { haptic(); setAdding(true); }}>
            + Qarz
          </button>
        )}
      </div>

      {!data ? (
        <Skeleton h={220} />
      ) : !data.items.length ? (
        <Card>
          <Empty icon="🤝" text={status === "open" ? "Ochiq qarzlar yo'q. Botga yozing: «Jasurga 100 ming qarz berdim 2 kunga»" : "Yopilgan qarzlar yo'q"} />
        </Card>
      ) : (
        <>
          {given.length > 0 && (
            <Card title={<>➡️ Sizga qaytarishlari kerak <span className="muted small">· {given.length} ta</span></>}>
              <div className="debts">
                {given.map((d) => (
                  <DebtRow key={d.id} d={d} onOpen={setOpen} />
                ))}
              </div>
            </Card>
          )}
          {taken.length > 0 && (
            <Card title={<>⬅️ Siz qaytarishingiz kerak <span className="muted small">· {taken.length} ta</span></>}>
              <div className="debts">
                {taken.map((d) => (
                  <DebtRow key={d.id} d={d} onOpen={setOpen} />
                ))}
              </div>
            </Card>
          )}
        </>
      )}
      <p className="hint center">🔔 Muddatgacha 3 kun qolganda va muddati o'tganda har kuni ertalab eslatma keladi.</p>

      <DebtSheet debt={open} onClose={() => setOpen(null)} onChanged={(m) => { setOpen(null); onChanged(m); }} />
      <AddDebtSheet open={adding} onClose={() => setAdding(false)} onDone={(m) => { setAdding(false); onChanged(m); }} />
    </>
  );
}

export function DebtSheet({ debt, onClose, onChanged }: { debt: Debt | null; onClose: () => void; onChanged: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [partial, setPartial] = useState("");
  const [due, setDue] = useState("");
  const [who, setWho] = useState("");
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState("");

  useEffect(() => {
    if (debt) {
      setPartial("");
      setDue(debt.due_at ? debt.due_at.slice(0, 10) : "");
      setWho(debt.counterparty);
      setNote(debt.note);
      setAmount(String(debt.amount));
    }
  }, [debt]);

  if (!debt) return null;
  const d = debt;

  async function run(fn: () => Promise<unknown>, msg: string) {
    setBusy(true);
    try {
      await fn();
      haptic("success");
      onChanged(msg);
    } catch (e) {
      haptic("error");
      onChanged(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  const payFull = () => run(() => api.post(`/api/debts/${d.id}/pay`, {}), "✅ Qarz yopildi");
  const payPart = () => {
    const a = parseInt(partial.replace(/\D/g, ""), 10);
    if (!a) return;
    return run(() => api.post(`/api/debts/${d.id}/pay`, { amount: a }), a >= d.remaining ? "✅ Qarz yopildi" : "✅ Qisman qaytarildi");
  };
  const save = () => {
    const a = parseInt(amount.replace(/\D/g, ""), 10);
    return run(
      () =>
        api.patch(`/api/debts/${d.id}`, {
          amount: a && a !== d.amount ? a : undefined,
          counterparty: who !== d.counterparty ? who : undefined,
          note: note !== d.note ? note : undefined,
          due_at: due && due !== (d.due_at || "").slice(0, 10) ? `${due}T12:00:00` : undefined,
          clear_due: !due && !!d.due_at,
        }),
      "✅ Saqlandi",
    );
  };
  const remove = async () => {
    if (!(await confirmDialog("Bu qarz yozuvi o'chirilsinmi?"))) return;
    return run(() => api.del(`/api/debts/${d.id}`), "🗑 O'chirildi");
  };
  const reopen = () => run(() => api.post(`/api/debts/${d.id}/reopen`), "↩️ Qayta ochildi");

  const tone = dueTone(d);
  return (
    <Sheet open={!!debt} onClose={onClose} title={d.direction === "given" ? "➡️ Siz bergan qarz" : "⬅️ Siz olgan qarz"}>
      <div className="debt-head">
        <div>
          <div className="debt-big">{money(d.remaining)}</div>
          <div className="muted small">
            {d.paid_amount > 0 ? `${num(d.paid_amount)} qaytarilgan · jami ${num(d.amount)}` : `berilgan: ${dateOf(d.occurred_at)}`}
          </div>
        </div>
        <span className={`pill tone-${tone}`}>{dueText(d)}</span>
      </div>

      {d.status === "open" ? (
        <>
          <button className="btn primary full mt" onClick={payFull} disabled={busy}>
            ✅ {d.direction === "given" ? "To'liq qaytardi" : "To'liq qaytardim"}
          </button>
          <label className="lbl">Qisman qaytarildi (so'm)</label>
          <div className="row gap">
            <input className="inp grow" inputMode="numeric" placeholder="masalan 50 000" value={partial ? num(parseInt(partial.replace(/\D/g, "") || "0", 10)) : ""} onChange={(e) => setPartial(e.target.value)} />
            <button className="btn" onClick={payPart} disabled={busy || !partial}>
              Qo'shish
            </button>
          </div>
        </>
      ) : (
        <button className="btn full mt" onClick={reopen} disabled={busy}>
          ↩️ Qayta ochish
        </button>
      )}

      <div className="divider" />
      <label className="lbl">Kim bilan</label>
      <input className="inp" value={who} maxLength={40} onChange={(e) => setWho(e.target.value)} placeholder="ism" />
      <label className="lbl">Summa (so'm)</label>
      <input className="inp" inputMode="numeric" value={num(parseInt(amount.replace(/\D/g, "") || "0", 10))} onChange={(e) => setAmount(e.target.value)} />
      <label className="lbl">Muddat</label>
      <div className="row gap">
        <input className="inp grow" type="date" value={due} min={todayISO()} onChange={(e) => setDue(e.target.value)} />
        {due && (
          <button className="btn" onClick={() => setDue("")}>
            ✕
          </button>
        )}
      </div>
      <label className="lbl">Izoh</label>
      <input className="inp" value={note} maxLength={60} onChange={(e) => setNote(e.target.value)} placeholder="ixtiyoriy" />
      <div className="row gap mt">
        <button className="btn danger" onClick={remove} disabled={busy}>
          🗑
        </button>
        <button className="btn primary grow" onClick={save} disabled={busy}>
          Saqlash
        </button>
      </div>
    </Sheet>
  );
}

export function AddDebtSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (m: string) => void }) {
  return (
    <Sheet open={open} onClose={onClose} title="Yangi qarz">
      <DebtForm onDone={onDone} active={open} />
    </Sheet>
  );
}

export function DebtForm({ onDone, active }: { onDone: (m: string) => void; active: boolean }) {
  const [direction, setDirection] = useState<"given" | "taken">("given");
  const [amount, setAmount] = useState("");
  const [who, setWho] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!active) {
      setAmount("");
      setWho("");
      setDue("");
      setNote("");
    }
  }, [active]);

  function quickDue(days: number) {
    const t = new Date();
    t.setDate(t.getDate() + days);
    setDue(`${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`);
  }

  async function save() {
    const a = parseInt(amount.replace(/\D/g, ""), 10);
    if (!a) return;
    setBusy(true);
    try {
      await api.post("/api/debts", { direction, amount: a, counterparty: who.trim(), note: note.trim(), due_at: due ? `${due}T12:00:00` : null });
      haptic("success");
      onDone("🤝 Qarz yozildi");
    } catch (e) {
      haptic("error");
      onDone(e instanceof ApiError && e.status === 402 ? "PRO kerak" : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="seg mb">
        <button className={direction === "given" ? "on" : ""} onClick={() => setDirection("given")}>
          ➡️ Men berdim
        </button>
        <button className={direction === "taken" ? "on" : ""} onClick={() => setDirection("taken")}>
          ⬅️ Men oldim
        </button>
      </div>
      <label className="lbl">Summa (so'm)</label>
      <input className="inp big" inputMode="numeric" placeholder="0" value={amount ? num(parseInt(amount.replace(/\D/g, "") || "0", 10)) : ""} onChange={(e) => setAmount(e.target.value)} />
      <label className="lbl">{direction === "given" ? "Kimga" : "Kimdan"}</label>
      <input className="inp" value={who} maxLength={40} onChange={(e) => setWho(e.target.value)} placeholder="ism" />
      <label className="lbl">Muddat</label>
      <div className="chips mb">
        {([[1, "ertaga"], [3, "3 kun"], [7, "1 hafta"], [14, "2 hafta"], [30, "1 oy"]] as Array<[number, string]>).map(([n, l]) => (
          <button key={n} className={`chip ${due && isDaysAhead(due, n) ? "on" : ""}`} onClick={() => quickDue(n)}>
            {l}
          </button>
        ))}
      </div>
      <input className="inp" type="date" value={due} min={todayISO()} onChange={(e) => setDue(e.target.value)} />
      <label className="lbl">Izoh</label>
      <input className="inp" value={note} maxLength={60} onChange={(e) => setNote(e.target.value)} placeholder="ixtiyoriy, masalan: telefon uchun" />
      <button className="btn primary full mt" onClick={save} disabled={busy || !amount}>
        Saqlash
      </button>
    </>
  );
}

function isDaysAhead(iso: string, days: number): boolean {
  const t = new Date();
  t.setDate(t.getDate() + days);
  return iso === `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
}
