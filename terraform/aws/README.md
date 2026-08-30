# AWS demo stack

Minimal **real AWS** deployment: one EC2 host, one Postgres server with **three databases** (`shop`, `billing`, `analytics`), S3 backups, seeded demo data.

No EKS, no NAT Gateway, no LocalStack — uses the default VPC and an EC2 instance profile for S3 access.

## What you get

| Resource | Purpose |
|----------|---------|
| `t4g.small` EC2 | Docker Compose: Postgres + backupper |
| S3 bucket | Compressed backups (`backups/{db_id}/…`) |
| IAM instance profile | S3 access without static AWS keys |
| 3 Postgres databases | `shop`, `billing`, `analytics` on one server |

**Estimated cost:** ~**$8–12/week** if you destroy when done (see `terraform output estimated_weekly_cost_usd`).

## Prerequisites

- AWS account + credentials configured locally (`aws configure`)
- Terraform >= 1.5
- An EC2 key pair is **not** required (bootstrap is fully automatic via user-data)

## Deploy

```bash
cd terraform/aws
terraform init
terraform apply
```

Review the plan, type `yes`. First boot takes **5–10 minutes** (Docker build + seed + first backup).

## Outputs

```bash
terraform output instance_public_ip
terraform output metrics_url
terraform output -raw postgres_password   # sensitive
terraform output ssh_command
```

Check bootstrap progress:

```bash
ssh ec2-user@$(terraform output -raw instance_public_ip)
sudo tail -f /var/log/idp-db-backupper-bootstrap.log
```

## Try it

```bash
IP=$(terraform output -raw instance_public_ip)
curl "http://${IP}:8080/health"
curl "http://${IP}:8080/ready"

ssh ec2-user@${IP}
cd /opt/idp-db-backupper/deploy/aws
docker compose exec backupper python manage.py list
docker compose exec backupper python manage.py status
docker compose exec backupper python manage.py daily
```

## Tear down (important!)

```bash
cd terraform/aws
terraform destroy
```

This deletes the EC2 instance and S3 bucket. Empty the bucket first if `terraform destroy` complains about non-empty state.

## Customize

| Variable | Default | Notes |
|----------|---------|-------|
| `aws_region` | `eu-central-1` | Pick a region close to you |
| `instance_type` | `t4g.small` | `t4g.medium` if builds feel slow |
| `ssh_cidr` | `0.0.0.0/0` | **Restrict to your IP** for demos |
| `repo_url` / `repo_ref` | this repo / `main` | Fork? Point at your fork |

```bash
terraform apply -var='ssh_cidr=203.0.113.10/32'
```

## Architecture note

“Three Postgres instances” here means **three logical databases** on one Postgres container — same layout as the kind/k8s demo, minimal RAM on a small EC2. Splitting into three separate RDS instances would cost ~3× more with little demo benefit.

## LocalStack terraform

The sibling directory `terraform/` (repo root) remains **LocalStack-only** for local dev. This `terraform/aws/` stack targets real AWS.
