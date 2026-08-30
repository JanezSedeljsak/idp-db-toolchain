# LocalStack Terraform (optional)

Bootstraps the **local dev** S3 bucket and IAM user against LocalStack.

Requires LocalStack running (`./dev.sh setup` or kind stack). Not used for production.

```bash
cd terraform/local
terraform init
terraform apply
```

`manage.py setup` also calls `ensure_bucket` — this is optional documentation of the IAM policy shape.
