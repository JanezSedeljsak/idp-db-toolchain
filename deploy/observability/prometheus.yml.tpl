global:
  scrape_interval: 30s
  evaluation_interval: 30s

rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  - job_name: db-toolchain
    metrics_path: /metrics
    scheme: ${metrics_scheme}
    static_configs:
      - targets: ["${metrics_target}"]
