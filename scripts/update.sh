#!/usr/bin/env bash
# Serverda yangilash: GitHub'dan oxirgi kodni olib, qayta build qiladi va saytni tekshiradi.
# Ishlatish: cd /opt/hisobchi && ./scripts/update.sh
# .env va backups/ git'da yo'q — ularga tegilmaydi.
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH="${BRANCH:-main}"
get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }
DOMAIN="$(get DOMAIN)"

echo "==> Zaxira (DB)"
./scripts/backup.sh || echo "   (zaxira o'tkazib yuborildi)"

echo "==> GitHub'dan yangilash ($BRANCH)"
git fetch --prune origin
git reset --hard "origin/$BRANCH"
chmod +x scripts/*.sh deploy/proxy/entrypoint.sh 2>/dev/null || true

echo "==> Build va qayta ishga tushirish"
docker compose build
docker compose up -d --remove-orphans
docker image prune -f >/dev/null 2>&1 || true

echo "==> API tayyor bo'lishini kutyapman…"
for i in $(seq 1 40); do
  st="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)" 2>/dev/null || echo starting)"
  [ "$st" = "healthy" ] && break
  sleep 3
done
echo "   api: ${st:-?}"

# Konteynerlar qayta yaratilganda IP o'zgaradi — proxy'ni yangi manzilga qayta yo'naltiramiz
docker compose exec -T proxy nginx -s reload >/dev/null 2>&1 || docker compose restart proxy >/dev/null 2>&1 || true
docker compose exec -T web nginx -s reload >/dev/null 2>&1 || true

echo "==> Sayt tekshiruvi"
./scripts/watchdog.sh --quiet && echo "   https://$DOMAIN — OK (200)" || echo "   [!] sayt javob bermadi, watchdog tiklashga urindi — logni tekshiring"

echo "==> Holat"
docker compose ps
echo "Tayyor: $(git log -1 --format='%h %s')"
