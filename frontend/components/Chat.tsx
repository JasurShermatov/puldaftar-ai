"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, ChatHistory, ChatMsg } from "@/lib/api";
import { confirmDialog, haptic } from "@/lib/tg";
import { SafeRich, Skeleton } from "./ui";

/** Foydalanuvchining o'z ma'lumotlari asosida javob beradigan AI suhbat. */
export default function Chat({ canAsk }: { canAsk: boolean }) {
  const [hist, setHist] = useState<ChatHistory | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    try {
      setHist(await api.get<ChatHistory>("/api/ai/chat"));
    } catch {
      setHist({ messages: [], suggestions: [], ai_enabled: false });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [hist?.messages.length, busy]);

  async function send(q?: string) {
    const msg = (q ?? text).trim();
    if (!msg || busy || !hist) return;
    if (!canAsk) {
      setErr("AI suhbat PRO foydalanuvchilar uchun.");
      return;
    }
    setErr(null);
    setText("");
    haptic();
    const optimistic: ChatMsg = { id: -Date.now(), role: "user", content: msg, created_at: new Date().toISOString() };
    setHist({ ...hist, messages: [...hist.messages, optimistic] });
    setBusy(true);
    try {
      const r = await api.post<{ answer: string; ai: boolean }>("/api/ai/chat", { message: msg });
      setHist((h) => (h ? { ...h, messages: [...h.messages, { id: -Date.now() - 1, role: "assistant", content: r.answer, created_at: new Date().toISOString() }] } : h));
      haptic("success");
    } catch (e) {
      haptic("error");
      setErr(e instanceof ApiError ? (e.status === 402 ? "AI suhbat PRO foydalanuvchilar uchun." : e.message) : "Javob olinmadi");
    } finally {
      setBusy(false);
      setTimeout(() => box.current?.focus(), 50);
    }
  }

  async function clear() {
    if (!(await confirmDialog("Suhbat tarixi o'chirilsinmi?"))) return;
    await api.del("/api/ai/chat");
    load();
  }

  if (!hist) return <Skeleton h={300} />;
  const empty = hist.messages.length === 0;

  return (
    <div className="chat">
      <div className="chat-log">
        {empty && (
          <div className="chat-intro">
            <div className="big-emoji">💬</div>
            <h3>Ma'lumotlaringiz asosida javob beraman</h3>
            <p className="muted small">
              Xarajat, daromad, kategoriyalar va qarzlaringizni ko'rib turib javob beraman. Yozuvlar ko'paygan sari javoblar aniqroq bo'ladi.
            </p>
          </div>
        )}
        {hist.messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.role === "assistant" ? <SafeRich html={m.content} /> : <span>{m.content}</span>}
          </div>
        ))}
        {busy && (
          <div className="msg assistant typing">
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={bottom} />
      </div>

      {(empty || hist.messages.length < 4) && hist.suggestions.length > 0 && (
        <div className="chips scroll">
          {hist.suggestions.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>
              {s}
            </button>
          ))}
        </div>
      )}
      {err && <p className="hint err">{err}</p>}
      {!hist.ai_enabled && <p className="hint">ℹ️ OpenAI kaliti ulanmagan — oddiy statistik javoblar beriladi.</p>}

      <div className="chat-input">
        <textarea
          ref={box}
          className="inp"
          rows={1}
          placeholder="Savol yozing…"
          value={text}
          maxLength={600}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="btn primary send" onClick={() => send()} disabled={busy || !text.trim()} aria-label="Yuborish">
          ➤
        </button>
      </div>
      {!empty && (
        <button className="link-btn" onClick={clear}>
          Tarixni tozalash
        </button>
      )}
    </div>
  );
}
