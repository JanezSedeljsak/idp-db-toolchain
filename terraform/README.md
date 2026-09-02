# Terraform

| Directory | Use |
|-----------|-----|
| [`demo/`](demo/) | Ephemeral EKS demo (`./dev.sh wizard-aws` / `aws-down`) |
| [`local/`](local/) | Optional LocalStack S3/IAM (not needed for `./dev.sh wizard`) |

Local dev: kind + LocalStack only. Production workload: provision S3 + IRSA for your EKS cluster, then apply `k8s/deploy/`.
