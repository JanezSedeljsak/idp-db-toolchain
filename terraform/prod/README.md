# Production AWS

S3 bucket, EKS IRSA role, optional EC2 host (Prometheus + Grafana). Assumes an **existing EKS cluster** for `k8s/deploy/`.

```bash
cd terraform/prod
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply
```

Wire up:

```bash
terraform output -raw db_toolchain_irsa_role_arn   # → k8s/deploy/serviceaccount.yaml
terraform output -json k8s_config_snippet          # → db-toolchain-config S3 bucket
```

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:<tag>
PUBLISH_TARGET=remote ./dev.sh ci-publish-deploy
```

Set `db_toolchain_metrics_target` to a host:port the observability EC2 can scrape (ALB, in-VPC IP, etc.).
