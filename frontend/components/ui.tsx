"use client";

import { ReactNode, useEffect } from "react";
import { haptic } from "@/lib/tg";

export function Card({ children, className = "", title, right }: { children: ReactNode; className?: string; title?: ReactNode; right?: ReactNode }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-h">
          <h3>{title}</h3>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: Array<[T, string]>; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="tablist">
      {options.map(([v, l]) => (
        <button
          key={v}
          role="tab"
          aria-selected={v === value}
          className={v === value ? "on" : ""}
          onClick={() => {
            haptic("select");
            onChange(v);
          }}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sheet-bg" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="sheet-grip" />
        <div className="sheet-h">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Yopish">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Spinner() {
  return <div className="spin" aria-label="Yuklanmoqda" />;
}

export function Skeleton({ h = 120 }: { h?: number }) {
  return <div className="skel" style={{ height: h }} />;
}

export function Toast({ text }: { text: string | null }) {
  if (!text) return null;
  return <div className="toast">{text}</div>;
}

export function Empty({ icon = "🗒", text }: { icon?: string; text: string }) {
  return (
    <div className="empty">
      <div className="empty-i">{icon}</div>
      <div>{text}</div>
    </div>
  );
}

/** Server faqat <b>/<i> qoldiradi; baribir mijoz tomonda ham tozalaymiz (XSS himoyasi). */
export function SafeRich({ html }: { html: string }) {
  const esc = html
    .replace(/&(?!(amp|lt|gt|quot|#39);)/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/&lt;(\/?)(b|i)&gt;/g, "<$1$2>")
    .replace(/\n/g, "<br/>");
  return <div className="rich" dangerouslySetInnerHTML={{ __html: esc }} />;
}
