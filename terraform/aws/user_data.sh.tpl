#!/bin/bash
set -euo pipefail

exec > >(tee /var/log/idp-db-backupper-bootstrap.log) 2>&1

AWS_REGION="${aws_region}"
S3_BUCKET="${s3_bucket}"
POSTGRES_PASSWORD="${postgres_password}"
REPO_URL="${repo_url}"
REPO_REF="${repo_ref}"
APP_DIR="/opt/idp-db-backupper"

dnf install -y docker git gettext
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.39.2/docker-compose-linux-aarch64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR/deploy/aws"

cat > .env <<EOF
AWS_REGION=${AWS_REGION}
S3_BUCKET=${S3_BUCKET}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
EOF

export AWS_REGION S3_BUCKET POSTGRES_PASSWORD
envsubst < backupper.toml.tpl > backupper.toml
chmod +x postgres-init/00-init.sh

docker compose build
docker compose up -d

echo "waiting for postgres..."
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U backupper >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "waiting for backupper..."
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

docker compose exec -T backupper python manage.py seed
docker compose exec -T backupper python manage.py daily

echo "bootstrap complete"
