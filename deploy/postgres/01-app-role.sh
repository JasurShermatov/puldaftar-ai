#!/bin/sh
# Ilova uchun alohida, RLS'ga bo'ysunadigan rol (jadval egasi emas, superuser emas).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
  DO \$\$BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_APP_ROLE}') THEN
      CREATE ROLE ${DB_APP_ROLE} LOGIN PASSWORD '${DB_APP_PASSWORD}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
  END\$\$;
  GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${DB_APP_ROLE};
SQL
