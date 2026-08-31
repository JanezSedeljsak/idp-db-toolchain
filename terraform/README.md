# Terraform

| Directory | Purpose |
|-----------|---------|
| [`local/`](local/) | **Optional** LocalStack bootstrap (S3 + IAM user). Dev works without this — `manage.py setup` creates the bucket. |
| [`demo/`](demo/) | **Ephemeral AWS demo** — EKS + S3 + ECR + IRSA + €20 budget alert. In-cluster Postgres (3 DBs), Prometheus, Grafana. See `./dev.sh wizard-aws`. |
| [`prod/`](prod/) | **Production AWS** — S3 backups bucket, EKS IRSA role, Prometheus + Grafana EC2 host |

**Local dev** uses kind + LocalStack (`./dev.sh wizard`). No AWS Terraform required.

**AWS demo** (`./dev.sh wizard-aws`) creates a throwaway EKS cluster and deploys the full in-cluster stack. Tear down with `./dev.sh aws-down`.

**Production** uses `terraform/prod` for AWS prerequisites, then `k8s/deploy/` for the idp-db-toolchain workload on EKS.
