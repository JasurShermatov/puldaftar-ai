export const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
export const MONTHS_FULL = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
export const WEEKDAYS = ["Yak", "Du", "Se", "Chor", "Pay", "Ju", "Sha"];

export function money(v: number): string {
  return `${Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ")} so'm`;
}

export function num(v: number): string {
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** Qisqa: 1.2 mln, 350 ming */
export function short(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000_000) return `${trim(v / 1_000_000_000)} mlrd`;
  if (a >= 1_000_000) return `${trim(v / 1_000_000)} mln`;
  if (a >= 1_000) return `${Math.round(v / 1_000)} ming`;
  return `${Math.round(v)}`;
}

function trim(x: number): string {
  return (Math.round(x * 10) / 10).toString();
}

/** "2026-09-30" ni lokal sana sifatida parse qilish (timezone siljishisiz) */
export function parseDay(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayLabel(s: string): string {
  const d = parseDay(s);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function monthLabel(s: string): string {
  const d = parseDay(s);
  return `${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`;
}

export function weekLabel(s: string): string {
  const d = parseDay(s);
  const e = new Date(d);
  e.setDate(d.getDate() + 6);
  return `${d.getDate()}.${pad(d.getMonth() + 1)}–${e.getDate()}.${pad(e.getMonth() + 1)}`;
}

export function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

/** ISO (offset bilan) → "HH:MM" user'ning o'z vaqti bo'yicha (server allaqachon user tz'da qaytaradi) */
export function timeOf(iso: string): string {
  return iso.slice(11, 16);
}

export function dateOf(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

export function relDay(iso: string, today: string): string {
  const d = iso.slice(0, 10);
  if (d === today) return "Bugun";
  const t = parseDay(today);
  t.setDate(t.getDate() - 1);
  const y = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
  if (d === y) return "Kecha";
  const dd = parseDay(d);
  return `${dd.getDate()} ${MONTHS_FULL[dd.getMonth()].toLowerCase()}, ${WEEKDAYS[dd.getDay()]}`;
}

export function todayISO(): string {
  const t = new Date();
  return `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
}
