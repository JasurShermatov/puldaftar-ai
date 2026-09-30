#!/usr/bin/env bash
# Let's Encrypt sertifikatini certbot bilan oladi (bir marta).
# Keyin yangilash avtomatik: certbot konteyneri har 12 soatda tekshiradi, proxy o'zi reload qiladi.
#   ./scripts/ssl.sh            — haqiqiy sertifikat
#   ./scripts/ssl.sh --staging  — sinov (limitga tushmaslik uchun)
set -euo pipefail
cd "$(dirname "$0")/.."

get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }
DOMAIN="$(get DOMAIN)"
EMAIL="$(get LETSENCRYPT_EMAIL)"
STAGING=""; [ "${1:-}" = "--staging" ] && STAGING="--staging"
[ -n "$DOMAIN" ] || { echo "[!] .env da DOMAIN yo'q"; exit 1; }

echo "==> DNS tekshiruvi: $DOMAIN"
MYIP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
DNSIP="$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)"
echo "    DNS: ${DNSIP:-topilmadi}   server: ${MYIP:-?}"
if [ -z "$DNSIP" ]; then
  echo "[!] $DOMAIN hali DNS da yo'q. Biroz kuting va qayta ishga tushiring."; exit 1
fi
if [ -n "$MYIP" ] && [ "$DNSIP" != "$MYIP" ]; then
  echo "[!] $DOMAIN boshqa IP ga qarayapti. Cloudflare'da A yozuvi $MYIP bo'lsin va DNS only (kulrang) qiling."; exit 1
fi

echo "==> Eski Caddy (bo'lsa) o'chirilmoqda"
docker ps -aq --filter label=com.docker.compose.project=hisobchi --filter label=com.docker.compose.service=caddy | xargs -r docker rm -f >/dev/null

echo "==> Proxy (HTTP) ishga tushirilmoqda"
docker compose up -d --remove-orphans proxy certbot
sleep 3

if [ -n "$EMAIL" ]; then EM=(--email "$EMAIL" --no-eff-email); else EM=(--register-unsafely-without-email); fi

echo "==> Certbot: sertifikat olinmoqda"
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot -d "$DOMAIN" \
  "${EM[@]}" --agree-tos --non-interactive --keep-until-expiring $STAGING

echo "==> HTTPS yoqilmoqda"
docker compose restart proxy
sleep 3
curl -sS -o /dev/null -w "    https://$DOMAIN -> HTTP %{http_code}\n" "https://$DOMAIN/" || true
echo "Tayyor. Yangilash avtomatik (certbot konteyneri)."
