# AWS demo (ephemeral EKS)

EKS + S3 + ECR + IRSA. In-cluster: Postgres (shop, billing, analytics), db-toolchain, Prometheus, Grafana. Budget email alert (~€20 threshold; does not auto-destroy).

```bash
cp terraform.tfvars.example terraform.tfvars   # set budget_email
./dev.sh wizard-aws
./dev.sh aws-down   # when finished
```

Rough cost for a few days: ~€7-15 (EKS control plane is the main line item).

```bash
kubectl port-forward -n idp-db-toolchain svc/grafana 3000:3000
kubectl port-forward -n idp-db-toolchain svc/prometheus 9090:9090
```

Grafana: http://localhost:3000 (`admin` / `admin`)
