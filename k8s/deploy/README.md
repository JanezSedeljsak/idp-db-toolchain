# Platform deploy

Workload manifests for production on **EKS**. Postgres and database URLs live outside this chart.

## AWS prerequisites (Terraform)

Run once per environment:

```bash
cd terraform/prod
terraform apply
```

Creates:

- S3 backup bucket (encrypted, versioned)
- IAM role for IRSA (`db_toolchain_irsa_role_arn` output)
- EC2 host with **Prometheus + Grafana** scraping your db-toolchain metrics endpoint

Patch `serviceaccount.yaml` with the IRSA role ARN and `db-toolchain-config.yaml` with the S3 bucket from terraform outputs.

## Before first kubectl deploy

1. **IRSA** — Create an IAM role with `k8s/deploy/irsa-policy.example.json`, trust your EKS OIDC provider, and set the role ARN in `serviceaccount.yaml`.
2. **Secrets** — Do not commit credentials. Use External Secrets (see `external-secret.example.yaml`) or create `db-toolchain-secrets` manually:

```bash
kubectl create secret generic db-toolchain-secrets -n idp-db-toolchain \
  --from-literal=DATABASES='[{"id":"shop","url":"postgres://..."}]' \
  --from-literal=NOTIFY_WEBHOOK_URL='' \
  --from-literal=ANONYMIZE_SALT='your-salt'
```

3. **Config** — Edit `db-toolchain-config.yaml` (`s3.bucket`, region). Database URLs come from the `DATABASES` env var (not the ConfigMap).
4. **No static AWS keys** — The pod uses the ServiceAccount + IRSA; omit `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

## Deploy

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:<tag>
export KUBECONFIG=/path/to/kubeconfig
./dev.sh ci-publish-deploy
```

## Alerting

Prometheus alert rules ship in `prometheus-rules.yaml`. Import into your platform Prometheus or scrape `db-toolchain:8080/metrics` and load the same rules:

| Alert | When |
|-------|------|
| `BackupperNotReady` | `/ready` failing 5m+ |
| `BackupperBackupStale` | No backup in 25h+ |
| `BackupperBackupFailures` | `failure_streak > 0` |
| `BackupperS3Unreachable` | S3 API check failing |
| `BackupperS3UploadError` | Latest failure looks S3-related |

Dev stack: view firing alerts at http://localhost:30909/alerts
