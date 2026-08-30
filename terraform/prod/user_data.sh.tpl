#!/bin/bash
set -euo pipefail

exec > >(tee /var/log/idp-observability-bootstrap.log) 2>&1

OBS_DIR="/opt/idp-observability"
mkdir -p "$OBS_DIR"

dnf install -y docker
systemctl enable --now docker

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.39.2/docker-compose-linux-aarch64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

cat > "$OBS_DIR/prometheus.yml" <<'EOF_PROM'
${prometheus_config}
EOF_PROM

cat > "$OBS_DIR/prometheus-rules.yml" <<'EOF_RULES'
${prometheus_rules}
EOF_RULES

cat > "$OBS_DIR/grafana-datasources.yml" <<'EOF_DS'
${grafana_datasources}
EOF_DS

cat > "$OBS_DIR/grafana-dashboards.yml" <<'EOF_DB'
${grafana_dashboards}
EOF_DB

cat > "$OBS_DIR/grafana-dashboard.json" <<'EOF_DASH'
${grafana_dashboard}
EOF_DASH

cat > "$OBS_DIR/docker-compose.yml" <<'EOF_COMPOSE'
${docker_compose}
EOF_COMPOSE

echo "GRAFANA_ADMIN_PASSWORD=${grafana_admin_password}" > "$OBS_DIR/.env"

cd "$OBS_DIR"
docker compose up -d

echo "observability stack started"
