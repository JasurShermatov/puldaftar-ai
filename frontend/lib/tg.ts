/* Telegram WebApp SDK ustidan yupqa wrapper (https://core.telegram.org/bots/webapps) */

type Haptic = {
  impactOccurred: (s: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred: (t: "error" | "success" | "warning") => void;
  selectionChanged: () => void;
};

export type TgWebApp = {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name?: string; username?: string } };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  version: string;
  platform: string;
  ready: () => void;
  expand: () => void;
  close: () => void;
  isVersionAtLeast: (v: string) => boolean;
  setHeaderColor?: (c: string) => void;
  setBackgroundColor?: (c: string) => void;
  onEvent: (e: string, cb: () => void) => void;
  offEvent: (e: string, cb: () => void) => void;
  HapticFeedback?: Haptic;
  BackButton?: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void };
  showConfirm?: (msg: string, cb: (ok: boolean) => void) => void;
  showAlert?: (msg: string, cb?: () => void) => void;
  openLink?: (url: string) => void;
  downloadFile?: (p: { url: string; file_name: string }, cb?: (ok: boolean) => void) => void;
  disableVerticalSwipes?: () => void;
};

declare global {
  interface Window {
    Telegram?: { WebApp: TgWebApp };
  }
}

export function tg(): TgWebApp | undefined {
  if (typeof window === "undefined") return undefined;
  return window.Telegram?.WebApp;
}

export function initData(): string {
  // Faqat Telegram imzolagan haqiqiy initData — hech qanday soxta/test qiymat yo'q
  return tg()?.initData || "";
}

export function haptic(kind: "light" | "success" | "error" | "select" = "light") {
  const h = tg()?.HapticFeedback;
  if (!h) return;
  try {
    if (kind === "success" || kind === "error") h.notificationOccurred(kind);
    else if (kind === "select") h.selectionChanged();
    else h.impactOccurred("light");
  } catch {
    /* eski klient */
  }
}

export function confirmDialog(msg: string): Promise<boolean> {
  const w = tg();
  if (w?.showConfirm && w.isVersionAtLeast?.("6.2")) {
    return new Promise((res) => w.showConfirm!(msg, (ok) => res(ok)));
  }
  return Promise.resolve(window.confirm(msg));
}

export function initTelegram() {
  const w = tg();
  if (!w) return;
  w.ready();
  w.expand();
  try {
    w.disableVerticalSwipes?.();
  } catch {
    /* noop */
  }
  applyTheme();
  w.onEvent("themeChanged", applyTheme);
}

function applyTheme() {
  const w = tg();
  if (!w) return;
  document.documentElement.dataset.theme = w.colorScheme === "dark" ? "dark" : "light";
  const bg = w.themeParams?.secondary_bg_color || w.themeParams?.bg_color;
  try {
    if (bg && w.isVersionAtLeast("6.1")) {
      w.setHeaderColor?.(bg);
      w.setBackgroundColor?.(bg);
    }
  } catch {
    /* noop */
  }
}

export function downloadFile(url: string, fileName: string): boolean {
  const w = tg();
  if (w?.downloadFile && w.isVersionAtLeast("8.0")) {
    w.downloadFile({ url, file_name: fileName });
    return true;
  }
  if (w?.openLink) {
    w.openLink(url);
    return true;
  }
  window.open(url, "_blank");
  return true;
}
