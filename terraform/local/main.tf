terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  access_key                  = "test"
  secret_key                  = "test"
  region                      = var.aws_region
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3  = var.localstack_endpoint
    iam = var.localstack_endpoint
  }
}

resource "aws_s3_bucket" "backups" {
  bucket = var.bucket_name

  tags = {
    Project     = "idp-db-toolchain"
    Environment = "local"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_iam_user" "db_toolchain" {
  name = "db-toolchain"
  path = "/"

  tags = {
    Project = "db-toolchain"
  }
}

resource "aws_iam_user_policy" "db_toolchain_s3" {
  name = "db-toolchain-s3"
  user = aws_iam_user.db_toolchain.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.backups.arn,
          "${aws_s3_bucket.backups.arn}/*"
        ]
      }
    ]
  })
}
