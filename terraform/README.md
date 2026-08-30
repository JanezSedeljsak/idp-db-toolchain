# LocalStack-only Terraform

This directory provisions the **local dev** S3 bucket and IAM user against LocalStack.
It uses hardcoded test credentials and has no remote state backend.

Do **not** run `terraform apply` against a real AWS account without reworking the provider,
backend, and credentials first.
