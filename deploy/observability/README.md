# Observability stack (production EC2)

Docker Compose files used by `terraform/prod` to run **Prometheus + Grafana** on AWS.

- Alert rules: `prometheus-rules.yml` (same rules as `k8s/prometheus-rules.yaml`)
- Dashboard: `grafana-dashboard.json`

Local kind dev uses in-cluster Prometheus/Grafana in `k8s/` instead — this directory is for the **production observability host** only.
