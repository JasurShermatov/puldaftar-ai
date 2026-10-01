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
  n=0; fails=0
  while :; do
    sleep 30
    n=$((n + 1))
    # upstream (web) tirikmi? 3 marta ketma-ket yiqilsa — DNS qayta o'qilishi uchun reload
    if wget -q -T 5 -O /dev/null "http://web:80/health/live" 2>/dev/null; then
      fails=0
    else
      fails=$((fails + 1))
      if [ "$fails" -ge 3 ]; then
        echo "proxy: upstream javob bermayapti, reload"
        nginx -s reload || true
        fails=0
      fi
    fi
    if [ $((n % 10)) -eq 0 ]; then       # har 5 daqiqada: sertifikat/konfig
      if render; then
        nginx -t && nginx -s reload || true
      elif [ -f /etc/letsencrypt/.renewed ]; then
        rm -f /etc/letsencrypt/.renewed
        echo "proxy: sertifikat yangilandi, reload"
        nginx -s reload || true
      fi
    fi
  done
) &

exec nginx -g 'daemon off;'
