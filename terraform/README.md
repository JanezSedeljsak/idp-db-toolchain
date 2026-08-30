# Terraform

| Directory | Purpose |
|-----------|---------|
| [`local/`](local/) | **Optional** LocalStack bootstrap (S3 + IAM user). Dev works without this — `manage.py setup` creates the bucket. |
| [`prod/`](prod/) | **Production AWS** — S3 backups bucket, EKS IRSA role, Prometheus + Grafana EC2 host |

**Local dev** uses kind + LocalStack (`./dev.sh wizard`). No AWS Terraform required.

**Production** uses `terraform/prod` for AWS prerequisites, then `k8s/deploy/` for the backupper workload on EKS.
