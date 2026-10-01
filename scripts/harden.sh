#!/usr/bin/env bash
# Server xavfsizligi va barqarorligi (Ubuntu/Debian, root). Bir marta: sudo ./scripts/harden.sh
#  1) UFW firewall: faqat 22 (SSH), 80, 443 ochiq
#  2) fail2ban: SSH parol/kalit brute-force'ga qarshi
#  3) unattended-upgrades: xavfsizlik yangilanishlari avtomatik
#  4) Docker log rotatsiyasi (disk to'lib qolmasin)
#  5) watchdog cron (har 2 daqiqada tekshiradi, yiqilsa tiklaydi, adminga xabar)
#  6) kunlik DB zaxira cron (03:00)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say() { printf "\033[1;32m==>\033[0m %s\n" "$*"; }
[ "$(id -u)" = 0 ] || { echo "root bilan ishga tushiring: sudo ./scripts/harden.sh"; exit 1; }

export DEBIAN_FRONTEND=noninteractive
say "Paketlar"
apt-get update -qq
apt-get install -y -qq ufw fail2ban unattended-upgrades cron curl >/dev/null || apt-get install -y ufw fail2ban unattended-upgrades cron curl
systemctl enable --now cron >/dev/null 2>&1 || true

say "Firewall (UFW): 22, 80, 443"
SSH_PORT="$( { grep -hE '^Port ' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null || true; } | awk '{print $2}' | head -1)"
SSH_PORT="${SSH_PORT:-22}"
echo "   SSH port: ${SSH_PORT}"
# Hozirgi SSH sessiya shu portdan kelayotganini tekshiramiz — aks holda o'zimizni qulflab qo'ymaylik
CUR_PORT="$(echo "${SSH_CONNECTION:-}" | awk '{print $4}')"
if [ -n "$CUR_PORT" ] && [ "$CUR_PORT" != "$SSH_PORT" ]; then
  echo "   [!] Siz ${CUR_PORT}-port orqali ulangansiz, konfiguratsiyada ${SSH_PORT}. Ikkalasi ham ochiq qoldiriladi."
  EXTRA_PORT="$CUR_PORT"
fi
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw limit "${SSH_PORT}/tcp" comment 'SSH (rate-limited)' >/dev/null
[ -n "${EXTRA_PORT:-}" ] && ufw limit "${EXTRA_PORT}/tcp" comment 'SSH (joriy sessiya)' >/dev/null
ufw allow 80/tcp comment 'HTTP' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw --force enable >/dev/null
# Docker UFW'ni chetlab o'tmasin: faqat proxy 80/443 ochadi, db/redis/api tashqariga port ochmaydi (compose'da yo'q)
ufw status | sed 's/^/   /'

say "fail2ban (sshd)"
cat > /etc/fail2ban/jail.d/hisobchi.conf <<CONF
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled = true
port    = ${SSH_PORT}
CONF
systemctl enable --now fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban || true

say "Avtomatik xavfsizlik yangilanishlari"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<CONF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

say "Docker log rotatsiyasi"
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<CONF
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
CONF
  echo "   /etc/docker/daemon.json yozildi (keyingi 'docker compose up -d --force-recreate' dan boshlab kuchga kiradi)"
else
  echo "   /etc/docker/daemon.json allaqachon bor — tegilmadi"
fi

say "Cron: watchdog (har 2 daqiqa) + zaxira (03:00)"
chmod +x "$ROOT"/scripts/*.sh
( crontab -l 2>/dev/null | grep -v 'hisobchi/scripts/watchdog.sh' | grep -v 'hisobchi/scripts/backup.sh' ;
  echo "*/2 * * * * $ROOT/scripts/watchdog.sh >> /var/log/hisobchi-watchdog.log 2>&1" ;
  echo "0 3 * * * cd $ROOT && ./scripts/backup.sh >> /var/log/hisobchi-backup.log 2>&1" ) | crontab -
crontab -l | sed 's/^/   /'

say "Tekshiruv"
"$ROOT/scripts/watchdog.sh" --quiet && echo "   sayt: OK" || echo "   [!] sayt javob bermadi — docker compose ps / logs"

cat <<MSG

──────────────────────────────────────────────────────────────
 ✅ Server himoyalandi
   Firewall: faqat ${SSH_PORT}, 80, 443 · fail2ban yoqildi · avto-yangilanish yoqildi
   Watchdog: har 2 daqiqada tekshiradi, yiqilsa tiklaydi va superadminga xabar beradi
   Zaxira: har kuni 03:00 → backups/ (7 kunlik + 4 haftalik)
   Loglar: /var/log/hisobchi-watchdog.log · /var/log/hisobchi-backup.log

 ⚠️ Tavsiya (qo'lda): SSH'da parol bilan kirishni o'chirish —
   /etc/ssh/sshd_config → PasswordAuthentication no → systemctl restart ssh
   (kalit bilan kirish ishlayotganiga ishonch hosil qilgach!)
──────────────────────────────────────────────────────────────
MSG
