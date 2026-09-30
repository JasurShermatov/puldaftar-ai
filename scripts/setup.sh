#!/usr/bin/env bash
# =====================================================================
#  Hisobchi AI — bir buyruq bilan o'rnatish (domen shart emas).
#
#  Serverda (Ubuntu/Debian VPS, 80 va 443 portlar ochiq):
#     cd hisobchi-ai && sudo ./scripts/setup.sh
#
#  O'z kompyuteringizda sinab ko'rish (ochiq IP kerak emas, Docker Desktop o'rnatilgan bo'lsin):
#     ./scripts/setup.sh --tunnel
#
#  Nima qiladi:
#   1) Docker yo'q bo'lsa o'rnatadi
#   2) .env yo'q/chala bo'lsa: kerakli maxfiy kalitlarni generatsiya qiladi
#   3) Server IP sini aniqlab, <ip>.sslip.io manzilini beradi (bepul, domen sotib olish shart emas).
#      Telegram Mini App faqat HTTPS da ishlaydi — Caddy shu manzilga Let's Encrypt sertifikatini o'zi oladi.
#   4) BOT_TOKEN / OPENAI_API_KEY bo'lmasa so'raydi
#   5) Hammasini ishga tushiradi va owner (superadmin) kodini ko'rsatadi
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="public"; [ "${1:-}" = "--tunnel" ] && MODE="tunnel"

say()  { printf "\033[1;32m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }

rand_hex() { openssl rand -hex "$1" 2>/dev/null || head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
rand_b64() { openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64; }

get()  { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'; }
put()  {  # put KEY VALUE  (qator bo'lsa almashtiradi, bo'lmasa qo'shadi)
  local k="$1" v="$2"
  if grep -qE "^$k=" .env; then
    python3 - "$k" "$v" <<'PY' 2>/dev/null || sed -i "s|^$k=.*|$k=$v|" .env
import sys, re
k, v = sys.argv[1], sys.argv[2]
s = open(".env").read()
s = re.sub(rf"^{re.escape(k)}=.*$", lambda m: f"{k}={v}", s, count=1, flags=re.M)
open(".env", "w").write(s)
PY
  else
    echo "$k=$v" >> .env
  fi
}
need() { [ -z "$(get "$1")" ]; }

# ---------- 1. Docker ----------
if ! command -v docker >/dev/null 2>&1; then
  if [ "$(uname)" = "Darwin" ]; then
    warn "Docker Desktop o'rnating: https://www.docker.com/products/docker-desktop/ va qayta ishga tushiring"; exit 1
  fi
  say "Docker o'rnatilmoqda…"
  if ! curl -fsSL https://get.docker.com | sh; then
    # Juda yangi Ubuntu versiyalarida (masalan 26.04) rasmiy skript hali qo'llab-quvvatlamasligi mumkin
    warn "get.docker.com ishlamadi — Ubuntu omboridan o'rnatilmoqda"
    apt-get update && apt-get install -y docker.io docker-compose-v2 || apt-get install -y docker.io docker-compose-plugin
    systemctl enable --now docker
  fi
fi
docker compose version >/dev/null 2>&1 || { warn "docker compose plugin topilmadi: apt-get install -y docker-compose-v2"; exit 1; }

# ---------- 1b. Swap (1-2 GB RAM li serverlarda build paytida xotira yetishmasligining oldini oladi) ----------
if [ "$(uname)" = "Linux" ] && [ "$(id -u)" = "0" ]; then
  MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
  SWAP_MB=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
  if [ "$MEM_MB" -lt 3000 ] && [ "$SWAP_MB" -lt 1000 ]; then
    say "RAM ${MEM_MB} MB — 2 GB swap qo'shilmoqda"
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
fi

# ---------- 2. .env ----------
[ -f .env ] || { cp .env.example .env; say ".env yaratildi"; }
chmod 600 .env

need POSTGRES_PASSWORD   && put POSTGRES_PASSWORD   "$(rand_hex 24)"
need DB_APP_PASSWORD     && put DB_APP_PASSWORD     "$(rand_hex 24)"
need DATA_ENCRYPTION_KEY && put DATA_ENCRYPTION_KEY "$(rand_b64)"
need HASH_SECRET         && put HASH_SECRET         "$(rand_hex 32)"
need WEBHOOK_SECRET      && put WEBHOOK_SECRET      "$(rand_hex 32)"
need BOT_MODE            && put BOT_MODE            "polling"

# ---------- 3. Manzil (domen yo'q → IP.sslip.io) ----------
if [ "$MODE" = "tunnel" ]; then
  put DOMAIN "localhost"
elif need DOMAIN || [ "$(get DOMAIN)" = "AUTO" ] || [ "$(get DOMAIN)" = "localhost" ]; then
  IP="${SERVER_IP:-$(curl -4 -fsS --max-time 8 https://api.ipify.org || curl -4 -fsS --max-time 8 https://ifconfig.me || true)}"
  if [ -z "$IP" ]; then read -rp "Serverning ochiq (public) IP manzili: " IP; fi
  put DOMAIN "${IP//./-}.sslip.io"
  say "Manzil: https://${IP//./-}.sslip.io  (IP: $IP)"
fi
[ "$MODE" = "public" ] && put PUBLIC_BASE_URL "https://$(get DOMAIN)"

# Domen serverga qaraganini tekshirish (HTTPS sertifikat olish uchun shart)
if [ "$MODE" = "public" ] && [[ "$(get DOMAIN)" != *".sslip.io" ]]; then
  MYIP="${SERVER_IP:-$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)}"
  DNSIP="$(getent hosts "$(get DOMAIN)" | awk '{print $1}' | head -1 || true)"
  if [ -n "$MYIP" ] && [ -n "$DNSIP" ] && [ "$MYIP" != "$DNSIP" ]; then
    warn "$(get DOMAIN) → $DNSIP, lekin server IP $MYIP."
    warn "Cloudflare'da A yozuvi $MYIP ga qarasin va bulut belgisi KULRANG (DNS only) bo'lsin, keyin qayta ishga tushiring."
  elif [ -z "$DNSIP" ]; then
    warn "$(get DOMAIN) hali topilmadi (DNS tarqalishi 5-30 daqiqa). Sertifikat DNS tayyor bo'lgach avtomatik olinadi."
  fi
fi

# ---------- 4. Tokenlar ----------
while need BOT_TOKEN; do read -rp "BOT_TOKEN (@BotFather): " t; put BOT_TOKEN "$t"; done
while need SUPERADMIN_IDS; do
  read -rp "Superadmin Telegram ID(lar)i, vergul bilan (@userinfobot dan bilasiz): " t || t=""
  t="$(echo "$t" | tr -d ' ')"
  [[ "$t" =~ ^[0-9]+(,[0-9]+)*$ ]] && put SUPERADMIN_IDS "$t" || warn "Faqat raqamlar, masalan: 123456789,987654321"
done
OK="$(get OPENAI_API_KEY)"
if [ -z "$OK" ] || [[ "$OK" == *"*"* ]]; then
  read -rp "OPENAI_API_KEY (sk-..., bo'sh qoldirsangiz ovoz/AI o'chiq ishlaydi): " t || t=""
  put OPENAI_API_KEY "$t"
fi

# ---------- 5. Ishga tushirish ----------
say "Build va ishga tushirish (birinchi marta 3-6 daqiqa)…"
if [ "$MODE" = "tunnel" ]; then
  docker compose stop caddy >/dev/null 2>&1 || true
  docker compose --profile tunnel up -d --build db redis migrate api worker web tunnel
  say "Tunnel manzilini kutyapman…"
  URL=""
  for i in $(seq 1 40); do
    URL="$(docker compose --profile tunnel logs tunnel 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
    [ -n "$URL" ] && break
    sleep 2
  done
  [ -n "$URL" ] || { warn "Tunnel manzili olinmadi: docker compose --profile tunnel logs tunnel"; exit 1; }
  put PUBLIC_BASE_URL "$URL"
  # yangi manzilni bot menyusiga yozish uchun api qayta yaratiladi
  docker compose --profile tunnel up -d --force-recreate api worker
else
  docker compose up -d --build
fi

say "API tayyor bo'lishini kutyapman…"
for i in $(seq 1 60); do
  if docker compose exec -T api curl -fs http://localhost:8000/health/ready >/dev/null 2>&1; then break; fi
  sleep 3
done
docker compose ps

cat <<MSG

──────────────────────────────────────────────────────────────
 ✅ Hisobchi AI ishga tushdi
    Mini App:   $(get PUBLIC_BASE_URL)
    (HTTPS sertifikat birinchi ochilishda 10-60 soniyada olinadi)

 🛡 Superadminlar (.env → SUPERADMIN_IDS): $(get SUPERADMIN_IDS)
    Botga /start, so'ng /admin → Sozlamalar: karta raqami, tariflar.
    Superadmin qo'shish/olib tashlash: .env dagi SUPERADMIN_IDS ni o'zgartiring → docker compose up -d

 Loglar:      docker compose logs -f api worker
 To'xtatish:  docker compose down
 Yangilash:   git pull (yoki fayllarni ko'chiring) && docker compose up -d --build
 ⚠️ .env dagi DATA_ENCRYPTION_KEY ni xavfsiz joyda zaxiralang.
──────────────────────────────────────────────────────────────
MSG
