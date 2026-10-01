#!/usr/bin/env bash
# Sayt/bot tirikligini tekshiradi; yiqilgan bo'lsa o'zi tiklaydi va superadminga Telegram orqali xabar beradi.
# O'rnatish (harden.sh buni o'zi qiladi):  */2 * * * * /opt/hisobchi/scripts/watchdog.sh >> /var/log/hisobchi-watchdog.log 2>&1
#   --quiet : faqat tekshiradi va tiklaydi, xabar yubormaydi (update.sh ichida ishlatiladi)
cd "$(dirname "$0")/.."
QUIET=0; [ "${1:-}" = "--quiet" ] && QUIET=1
get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }
DOMAIN="$(get DOMAIN)"; TOKEN="$(get BOT_TOKEN)"; ADMIN="$(get SUPERADMIN_IDS | tr -d ' ' | cut -d, -f1)"
URL="https://$DOMAIN/health/ready"
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo 000; }

notify() {
  [ "$QUIET" = 1 ] && return 0
  [ -n "$TOKEN" ] && [ -n "$ADMIN" ] || return 0
  curl -s --max-time 10 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d "chat_id=$ADMIN" -d "parse_mode=HTML" --data-urlencode "text=$1" >/dev/null 2>&1 || true
}

c="$(code)"
if [ "$c" = "200" ]; then
  # api ichki holati ham sog'lommi?
  st="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api 2>/dev/null)" 2>/dev/null || echo unknown)"
  [ "$st" = "unhealthy" ] || exit 0
fi

echo "$(date -Is) health=$c api=${st:-?} → tiklash"
docker compose up -d --remove-orphans >/dev/null 2>&1 || true
# api yiqilgan bo'lsa — qayta ishga tushiramiz
st="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api 2>/dev/null)" 2>/dev/null || echo unknown)"
if [ "$st" = "unhealthy" ] || [ "$c" = "000" ] || [ "$c" = "502" ] || [ "$c" = "504" ]; then
  [ "$st" = "unhealthy" ] && docker compose restart api >/dev/null 2>&1
  docker compose exec -T proxy nginx -s reload >/dev/null 2>&1 || docker compose restart proxy >/dev/null 2>&1
  docker compose exec -T web nginx -s reload >/dev/null 2>&1 || docker compose restart web >/dev/null 2>&1
fi
sleep 8
c2="$(code)"
[ "$c2" = "200" ] && [ "$c" != "200" ] && c2="200 (tiklandi)"
echo "$(date -Is) tiklashdan keyin: $c2"
if [ "$c2" = "200 (tiklandi)" ] || [ "$c2" = "200" ]; then
  notify "⚠️ <b>PulDaftar watchdog</b>%0ASayt javob bermadi (HTTP $c, api=${st:-?}).%0A✅ Avtomatik tiklandi."
  exit 0
fi
notify "🚨 <b>PulDaftar watchdog</b>%0ASayt ishlamayapti (HTTP $c → $c2).%0AServerda tekshiring: docker compose ps / logs"
exit 1
