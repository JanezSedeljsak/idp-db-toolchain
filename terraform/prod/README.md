# Production AWS infrastructure

Terraform for **real AWS** — not used for local dev (use kind + LocalStack instead).

## What it creates

| Resource | Purpose |
|----------|---------|
| **S3 bucket** | Encrypted, versioned backup storage |
| **IAM role (IRSA)** | EKS ServiceAccount → S3 access (no static AWS keys) |
| **EC2 observability host** | Prometheus + Grafana (Docker Compose) |

Local dev uses **kind** (`k8s/`) with in-cluster Prometheus/Grafana — no AWS Terraform required.

## Prerequisites

- AWS credentials with permission to create S3, IAM, EC2
- An **existing EKS cluster** where `k8s/deploy/` runs the idp-db-toolchain workload
- Network path from the observability EC2 host to your db-toolchain metrics endpoint

## Apply

```bash
cd terraform/prod
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars — eks_cluster_name, admin_cidr, db_toolchain_metrics_target

terraform init
terraform apply
```

## Wire up Kubernetes

After apply:

```bash
# IRSA role on the ServiceAccount
terraform output -raw db_toolchain_irsa_role_arn
# → patch k8s/deploy/serviceaccount.yaml

# S3 bucket in ConfigMap
terraform output -json k8s_config_snippet

# Grafana
terraform output grafana_url
terraform output -raw grafana_admin_password
```

Deploy the workload:

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:<tag>
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

## Metrics scrape target

Set `db_toolchain_metrics_target` to whatever Prometheus can reach from the observability host, e.g.:

- Internal ALB: `internal-db-toolchain-1234567890.eu-central-1.elb.amazonaws.com:8080`
- In-VPC private IP of a db-toolchain pod (less stable)
- VPN-reachable hostname

Prometheus scrapes `http(s)://<target>/metrics` with alert rules from `deploy/observability/prometheus-rules.yml`.

## Tear down

```bash
terraform destroy
```

Empty the S3 bucket first if `force_destroy` is not enabled.
