#!/bin/sh
# Foydalanish: ./scripts/restore.sh backups/hisobchi_20260930_0300.sql.gz
set -e
cd "$(dirname "$0")/.."
. ./.env
[ -f "$1" ] || { echo "fayl topilmadi"; exit 1; }
docker compose stop api worker
gunzip -c "$1" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose run --rm migrate
docker compose start api worker
