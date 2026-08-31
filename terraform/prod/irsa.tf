data "aws_eks_cluster" "cluster" {
  name = var.eks_cluster_name
}

data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer
}

locals {
  oidc_provider_host = replace(data.aws_iam_openid_connect_provider.eks.url, "https://", "")
}

resource "aws_iam_role" "db_toolchain" {
  name = "${var.name_prefix}-${var.environment}-db-toolchain"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = data.aws_iam_openid_connect_provider.eks.arn
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

  tags = {
    Project     = "idp-db-toolchain"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "db_toolchain_s3" {
  name = "${var.name_prefix}-${var.environment}-s3"
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
