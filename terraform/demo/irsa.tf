locals {
  oidc_provider_host = replace(module.eks.cluster_oidc_issuer_url, "https://", "")
}

resource "aws_iam_role" "db_toolchain" {
  name = "${var.name_prefix}-demo-db-toolchain"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.oidc_provider_host}:aud" = "sts.amazonaws.com"
            "${local.oidc_provider_host}:sub" = "system:serviceaccount:${var.k8s_namespace}:${var.k8s_service_account}"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "db_toolchain_s3" {
  name = "${var.name_prefix}-demo-s3"
  role = aws_iam_role.db_toolchain.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject",
          "s3:HeadBucket"
        ]
        Resource = [
          aws_s3_bucket.backups.arn,
          "${aws_s3_bucket.backups.arn}/*"
        ]
      }
    ]
  })
}
