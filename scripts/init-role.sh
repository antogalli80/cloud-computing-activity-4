#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE cloud_app LOGIN PASSWORD :'app_password';
CREATE DATABASE cloud3_test OWNER cloud_admin;
SQL
