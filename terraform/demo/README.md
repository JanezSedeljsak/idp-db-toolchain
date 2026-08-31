# AWS demo stack (ephemeral EKS)

Creates a **short-lived** EKS cluster with the full in-cluster demo:

- Postgres with **shop**, **billing**, **analytics**
- **db-toolchain** → real S3 backups (IRSA)
- **Prometheus** + **Grafana** in the same namespace
- ECR for the app image
- AWS Budget alert (default **€20**/month threshold — alerts only, does not auto-destroy)

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity`)
- Terraform >= 1.5
- `kubectl`, `docker`

## Quick start

```bash
cp terraform/demo/terraform.tfvars.example terraform/demo/terraform.tfvars
# edit budget_email

./dev.sh wizard-aws
```

When finished:

```bash
./dev.sh aws-down
```

## Rough cost (2–3 days)

| Item | ~cost |
|------|--------|
| EKS control plane | ~€5–7 |
| 1× `t4g.medium` node | ~€1–2 |
| S3 + ECR | &lt; €1 |
| In-cluster Postgres / Prom / Grafana | included on the node |

**No NAT Gateway, no RDS, no separate observability EC2** — keeps the demo inside the €20 alert envelope for a few days if you tear down promptly.

## Access Grafana / Prometheus

After `wizard-aws`:

```bash
kubectl port-forward -n idp-db-toolchain svc/grafana 3000:3000
kubectl port-forward -n idp-db-toolchain svc/prometheus 9090:9090
```

Grafana: http://localhost:3000 (`admin` / `admin`)
