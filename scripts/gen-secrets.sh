#!/bin/sh
# .env uchun barcha maxfiy qiymatlarni generatsiya qiladi (nusxa olib qo'ying)
echo "WEBHOOK_SECRET=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
echo "DB_APP_PASSWORD=$(openssl rand -hex 24)"
echo "DATA_ENCRYPTION_KEY=$(python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')"
echo "HASH_SECRET=$(openssl rand -hex 32)"
