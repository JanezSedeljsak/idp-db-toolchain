#!/bin/bash
set -euo pipefail
for db in shop billing analytics; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -d postgres \
    -tc "SELECT 1 FROM pg_database WHERE datname = '${db}'" | grep -q 1 \
    || psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -d postgres -c "CREATE DATABASE ${db}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -d "${db}" \
    -f /docker-entrypoint-initdb.d/01-schema.sql
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -d "${db}" \
    -f /docker-entrypoint-initdb.d/02-anonymize.sql
done
