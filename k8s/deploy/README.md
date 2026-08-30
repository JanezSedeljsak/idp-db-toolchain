# Platform deploy

Workload-only manifests for production. Postgres, S3, and credentials live outside this chart.

Platform engineers must create the `backupper-env` secret in the target namespace before the first deploy (see `../backupper-secret.yaml` for the expected keys — point `DATABASE_URL` at your internal Postgres).

```bash
export IMAGE=ghcr.io/your-org/idp-db-backupper:<tag>
export KUBECONFIG=/path/to/kubeconfig
./dev.sh ci-publish-deploy
```

Deploy uses a RollingUpdate Deployment: the new pod must pass readiness before the old pod is removed and Service endpoints switch over.
