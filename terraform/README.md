# Terraform

| Directory | Use |
|-----------|-----|
| [`demo/`](demo/) | Ephemeral EKS demo (`./dev.sh wizard-aws` / `aws-down`) |
| [`prod/`](prod/) | S3, IRSA, observability EC2 for platform EKS |
| [`local/`](local/) | Optional LocalStack S3/IAM (not needed for `./dev.sh wizard`) |

Local dev: kind + LocalStack only. Production workload: `terraform/prod` + `k8s/deploy/`.
