#!/bin/sh
# Tashqi nginx (80/443). Sertifikat bo'lmasa — faqat HTTP (+ ACME challenge),
# certbot sertifikat olgach — avtomatik HTTPS ga o'tadi. Yangilangan sertifikatni o'zi reload qiladi.
set -eu
: "${DOMAIN:?DOMAIN .env da berilmagan}"
T=/etc/hisobchi-proxy
OUT=/etc/nginx/conf.d/default.conf
LIVE="/etc/letsencrypt/live/$DOMAIN"

render() {  # konfiguratsiya o'zgarsa 0 qaytaradi
  if [ -s "$LIVE/fullchain.pem" ] && [ -s "$LIVE/privkey.pem" ]; then
    src="$T/https.conf.template"; mode=https
  else
    src="$T/http.conf.template"; mode=http
  fi
  envsubst '${DOMAIN}' < "$src" > "$OUT.new"
  if cmp -s "$OUT.new" "$OUT" 2>/dev/null; then rm -f "$OUT.new"; return 1; fi
  mv "$OUT.new" "$OUT"
  echo "proxy: $DOMAIN -> $mode rejimi"
  return 0
}

render || true
nginx -t

(
  while :; do
    sleep 300
    if render; then
      nginx -t && nginx -s reload || true
    elif [ -f /etc/letsencrypt/.renewed ]; then
      rm -f /etc/letsencrypt/.renewed
      echo "proxy: sertifikat yangilandi, reload"
      nginx -s reload || true
    fi
  done
) &

exec nginx -g 'daemon off;'
