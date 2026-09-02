# Platform deploy (EKS)

App workload only. Postgres and `DATABASES` URLs live outside this chart.

1. Provision S3 + IRSA for the platform EKS cluster.
2. Patch `serviceaccount.yaml` (IRSA ARN) and `db-toolchain-config.yaml` (S3 bucket).
3. Create `db-toolchain-secrets` (see `external-secret.example.yaml`) with `DATABASES` JSON.
4. Deploy:

```bash
export IMAGE=ghcr.io/your-org/idp-db-toolchain:<tag>
./dev.sh ci-publish-deploy
```

Alert rules: `../prometheus-rules.yaml` (or scrape `:8080/metrics`).
