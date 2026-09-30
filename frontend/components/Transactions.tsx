"use client";

import { useEffect, useMemo, useState } from "react";
import { api, Category, IngestResult, Tx } from "@/lib/api";
import { money, num, relDay, timeOf } from "@/lib/format";
import { confirmDialog, haptic } from "@/lib/tg";
import { Empty, Sheet } from "./ui";

/** Kunlar bo'yicha guruhlangan ro'yxat */
export function TxList({ items, today, onOpen }: { items: Tx[]; today: string; onOpen: (t: Tx) => void }) {
  const groups = useMemo(() => {
    const m = new Map<string, Tx[]>();
    for (const t of items) {
      const d = t.occurred_at.slice(0, 10);
      if (!m.has(d)) m.set(d, []);
      m.get(d)!.push(t);
    }
    return [...m.entries()];
  }, [items]);

  if (!items.length) return <Empty text="Bu davrda yozuvlar yo'q. Botga yozing yoki «+» ni bosing." />;

  return (
    <div className="txlist">
      {groups.map(([day, list]) => {
        const exp = list.filter((t) => t.type === "expense").reduce((s, t) => s + t.amount, 0);
        return (
          <div key={day} className="txgroup">
            <div className="txgroup-h">
              <span>{relDay(day, today)}</span>
              <span className="muted">−{num(exp)}</span>
            </div>
            {list.map((t) => (
              <button key={t.id} className="tx" onClick={() => onOpen(t)}>
                <span className="tx-ic">{t.category_emoji || "•"}</span>
                <span className="tx-main">
                  <span className="tx-name">{t.category_name || "Boshqa"}</span>
                  <span className="tx-sub">
                    {timeOf(t.occurred_at)}
                    {t.description ? ` · ${t.description}` : ""}
                    {t.source === "voice" ? " · 🎙" : ""}
                  </span>
                </span>
                <span className={`tx-amt ${t.type}`}>
                  {t.type === "income" ? "+" : "−"}
                  {num(t.amount)}
                </span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export function TxEditSheet({ tx, categories, onClose, onChanged }: { tx: Tx | null; categories: Category[]; onClose: () => void; onChanged: (msg: string) => void }) {
  const [amount, setAmount] = useState("");
  const [desc, setDesc] = useState("");
  const [cat, setCat] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (tx) {
      setAmount(String(tx.amount));
      setDesc(tx.description || "");
      setCat(tx.category_id);
    }
  }, [tx]);

  if (!tx) return null;
  const cats = categories.filter((c) => c.type === tx.type && c.is_active);

  async function save() {
    if (!tx) return;
    const a = parseInt(amount.replace(/\D/g, ""), 10);
    if (!a || a <= 0) return;
    setBusy(true);
    try {
      await api.patch(`/api/transactions/${tx.id}`, {
        amount: a !== tx.amount ? a : undefined,
        category_id: cat !== tx.category_id ? cat : undefined,
        description: desc !== tx.description ? desc : undefined,
      });
      haptic("success");
      onChanged("✅ Saqlandi");
      onClose();
    } catch {
      haptic("error");
      onChanged("Xatolik yuz berdi");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!tx) return;
    if (!(await confirmDialog("Bu yozuv o'chirilsinmi?"))) return;
    setBusy(true);
    try {
      await api.del(`/api/transactions/${tx.id}`);
      haptic("success");
      onChanged("🗑 O'chirildi");
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={!!tx} onClose={onClose} title="Yozuvni tahrirlash">
      <label className="lbl">Summa (so'm)</label>
      <input className="inp big" inputMode="numeric" value={num(parseInt(amount.replace(/\D/g, "") || "0", 10))} onChange={(e) => setAmount(e.target.value)} />
      <label className="lbl">Izoh</label>
      <input className="inp" value={desc} maxLength={120} onChange={(e) => setDesc(e.target.value)} placeholder="masalan: taksi" />
      <label className="lbl">Kategoriya</label>
      <div className="chips">
        {cats.map((c) => (
          <button key={c.id} className={`chip ${c.id === cat ? "on" : ""}`} onClick={() => setCat(c.id)}>
            {c.emoji} {c.name}
          </button>
        ))}
      </div>
      <div className="row gap mt">
        <button className="btn danger" onClick={remove} disabled={busy}>
          🗑 O'chirish
        </button>
        <button className="btn primary grow" onClick={save} disabled={busy}>
          Saqlash
        </button>
      </div>
    </Sheet>
  );
}

export function AddSheet({ open, onClose, categories, onDone }: { open: boolean; onClose: () => void; categories: Category[]; onDone: (msg: string) => void }) {
  const [mode, setMode] = useState<"text" | "manual">("text");
  const [text, setText] = useState("");
  const [amount, setAmount] = useState("");
  const [type, setType] = useState<"expense" | "income">("expense");
  const [cat, setCat] = useState<number | null>(null);
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);

  useEffect(() => {
    if (!open) {
      setText("");
      setResult(null);
      setAmount("");
      setDesc("");
      setCat(null);
    }
  }, [open]);

  async function sendText() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await api.post<IngestResult>("/api/transactions/text", { text });
      setResult(r);
      if (r.kind === "saved" && !r.pending_id) {
        haptic("success");
        onDone(`✅ ${r.saved.length} ta yozuv saqlandi`);
        onClose();
      }
    } catch (e) {
      haptic("error");
      onDone((e as Error).message || "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(ok: boolean) {
    if (!result?.pending_id) return;
    setBusy(true);
    try {
      if (ok) await api.post(`/api/pending/${result.pending_id}/confirm`);
      else await api.del(`/api/pending/${result.pending_id}`);
      onDone(ok ? "✅ Saqlandi" : "Bekor qilindi");
      onClose();
    } finally {
      setBusy(false);
    }
  }

  async function pickAmount(v: number) {
    if (!result?.pending_id) return;
    setBusy(true);
    try {
      await api.post(`/api/pending/${result.pending_id}/amount/${v}`);
      onDone("✅ Saqlandi");
      onClose();
    } finally {
      setBusy(false);
    }
  }

  async function sendManual() {
    const a = parseInt(amount.replace(/\D/g, ""), 10);
    if (!a || !cat) return;
    setBusy(true);
    try {
      await api.post("/api/transactions", { amount: a, category_id: cat, description: desc });
      haptic("success");
      onDone("✅ Saqlandi");
      onClose();
    } catch (e) {
      onDone((e as Error).message || "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  const cats = categories.filter((c) => c.type === type && c.is_active);

  return (
    <Sheet open={open} onClose={onClose} title="Yangi yozuv">
      <div className="seg mb">
        <button className={mode === "text" ? "on" : ""} onClick={() => setMode("text")}>
          ✍️ Oddiy matn
        </button>
        <button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")}>
          🧾 Qo'lda
        </button>
      </div>

      {mode === "text" ? (
        <>
          <textarea
            className="inp area"
            placeholder="Masalan: taksiga 35 ming, obedga 80 ming ketdi"
            value={text}
            maxLength={1000}
            onChange={(e) => setText(e.target.value)}
            autoFocus
          />
          <p className="hint">💡 Ovoz bilan yozish uchun — botga ovozli xabar yuboring.</p>
          {result && result.kind !== "saved" && (
            <div className="notice">
              {result.kind === "expired" && <p>⌛️ Bepul davr tugagan. Botdagi «💳 Obuna» tugmasi orqali PRO ni faollashtiring.</p>}
              {result.kind === "pending" && (
                <>
                  <p>
                    <b>Shu to'g'rimi?</b>
                  </p>
                  {result.pending_items.map((p, i) => (
                    <p key={i}>
                      {p.category_emoji} {p.category_name} — {money(p.amount)} {p.description ? `· ${p.description}` : ""}
                    </p>
                  ))}
                  {result.question && <p className="muted">❔ {result.question}</p>}
                  <div className="row gap mt">
                    <button className="btn" onClick={() => confirm(false)} disabled={busy}>
                      Bekor
                    </button>
                    <button className="btn primary grow" onClick={() => confirm(true)} disabled={busy}>
                      ✅ Tasdiqlash
                    </button>
                  </div>
                </>
              )}
              {result.kind === "clarify" && (
                <>
                  <p>❔ {result.question}</p>
                  {result.amount_options.length > 0 && (
                    <div className="row gap mt">
                      {result.amount_options.map((v) => (
                        <button key={v} className="btn grow" onClick={() => pickAmount(v)} disabled={busy}>
                          {money(v)}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
              {result.kind === "duplicate" && <p>Bu allaqachon saqlangan.</p>}
            </div>
          )}
          {!(result && result.kind === "pending") && (
            <button className="btn primary full mt" onClick={sendText} disabled={busy || !text.trim()}>
              {busy ? "Hisoblayapman…" : "Saqlash"}
            </button>
          )}
        </>
      ) : (
        <>
          <div className="seg mb">
            <button className={type === "expense" ? "on" : ""} onClick={() => { setType("expense"); setCat(null); }}>
              💸 Xarajat
            </button>
            <button className={type === "income" ? "on" : ""} onClick={() => { setType("income"); setCat(null); }}>
              💰 Daromad
            </button>
          </div>
          <label className="lbl">Summa (so'm)</label>
          <input className="inp big" inputMode="numeric" placeholder="0" value={amount ? num(parseInt(amount.replace(/\D/g, "") || "0", 10)) : ""} onChange={(e) => setAmount(e.target.value)} />
          <label className="lbl">Izoh</label>
          <input className="inp" value={desc} maxLength={120} onChange={(e) => setDesc(e.target.value)} placeholder="ixtiyoriy" />
          <label className="lbl">Kategoriya</label>
          <div className="chips">
            {cats.map((c) => (
              <button key={c.id} className={`chip ${c.id === cat ? "on" : ""}`} onClick={() => setCat(c.id)}>
                {c.emoji} {c.name}
              </button>
            ))}
          </div>
          <button className="btn primary full mt" onClick={sendManual} disabled={busy || !amount || !cat}>
            Saqlash
          </button>
        </>
      )}
    </Sheet>
  );
}
