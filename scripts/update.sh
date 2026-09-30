#!/usr/bin/env bash
# Serverda yangilash: GitHub'dan oxirgi kodni olib, qayta build qiladi.
# Ishlatish: cd /opt/hisobchi && ./scripts/update.sh
# .env va backups/ git'da yo'q — ularga tegilmaydi.
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH="${BRANCH:-main}"
echo "==> Zaxira (DB)"
./scripts/backup.sh || echo "   (zaxira o'tkazib yuborildi)"

echo "==> GitHub'dan yangilash ($BRANCH)"
git fetch --prune origin
git reset --hard "origin/$BRANCH"

echo "==> Build va qayta ishga tushirish"
docker compose build
docker compose up -d --remove-orphans
docker image prune -f >/dev/null 2>&1 || true

echo "==> Holat"
docker compose ps
echo "Tayyor: $(git log -1 --format='%h %s')"
