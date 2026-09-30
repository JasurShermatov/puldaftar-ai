"use client";

import { useCallback, useEffect, useState } from "react";
import AdminApp from "./AdminApp";
import UserApp from "./UserApp";
import { Spinner } from "./ui";
import { api, ApiError, Me } from "@/lib/api";
import { initData, initTelegram, tg } from "@/lib/tg";

/** Telegram ichida ochilganini tekshiradi, /api/me ni yuklaydi va kerakli ilovani ko'rsatadi. */
export default function Boot({ mode }: { mode: "user" | "admin" }) {
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState<"outside" | "blocked" | "auth" | "network" | "forbidden" | null>(null);

  const load = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/api/me"));
    } catch (e) {
      if (e instanceof ApiError) setErr(e.status === 403 ? "blocked" : e.status === 401 ? "auth" : "network");
      else setErr("network");
    }
  }, []);

  useEffect(() => {
    initTelegram();
    // SDK skripti kechikishi mumkin — bir oz kutamiz
    let tries = 0;
    const tick = () => {
      if (initData()) return load();
      if (++tries > 20) return setErr("outside");
      setTimeout(tick, 50);
    };
    tick();
    const w = tg();
    if (w?.BackButton && mode === "admin") {
      const back = () => (window.location.href = "/");
      w.BackButton.show();
      w.BackButton.onClick(back);
      return () => {
        w.BackButton?.offClick(back);
        w.BackButton?.hide();
      };
    }
  }, [load, mode]);

  if (err) {
    const msg = {
      outside: ["📱", "Ilovani Telegram ichida oching", "Botdagi «📊 Dashboard» tugmasini bosing."],
      blocked: ["⛔️", "Hisobingiz bloklangan", "Savollar bo'lsa admin bilan bog'laning."],
      auth: ["🔐", "Sessiya eskirgan", "Ilovani yopib, botdan qaytadan oching."],
      network: ["📡", "Server bilan aloqa yo'q", "Internetni tekshirib, qayta urinib ko'ring."],
      forbidden: ["🛡", "Ruxsat yo'q", "Bu bo'lim faqat admin uchun."],
    }[err];
    return (
      <div className="center-screen">
        <div className="big-emoji">{msg[0]}</div>
        <h2>{msg[1]}</h2>
        <p className="muted">{msg[2]}</p>
        {err === "network" && (
          <button className="btn primary mt" onClick={() => { setErr(null); load(); }}>
            Qayta urinish
          </button>
        )}
      </div>
    );
  }
  if (!me) {
    return (
      <div className="center-screen">
        <Spinner />
      </div>
    );
  }
  if (mode === "admin") {
    if (!me.is_admin) {
      return (
        <div className="center-screen">
          <div className="big-emoji">🛡</div>
          <h2>Ruxsat yo'q</h2>
          <p className="muted">Bu bo'lim faqat superadmin uchun.</p>
        </div>
      );
    }
    return <AdminApp />;
  }
  return <UserApp me={me} reloadMe={load} />;
}
