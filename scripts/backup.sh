#!/bin/sh
# Kunlik zaxira (cron: 0 3 * * * /opt/hisobchi/scripts/backup.sh). 7 kunlik + 4 haftalik saqlanadi.
set -e
cd "$(dirname "$0")/.."
. ./.env
mkdir -p backups
F="backups/hisobchi_$(date +%Y%m%d_%H%M).sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner | gzip > "$F"
# ixtiyoriy: shifrlash — gpg --symmetric "$F"
find backups -name 'hisobchi_*.sql.gz' -mtime +7 ! -name '*_0300*' -delete 2>/dev/null || true
find backups -name 'hisobchi_*.sql.gz' -mtime +31 -delete 2>/dev/null || true
echo "backup: $F"
