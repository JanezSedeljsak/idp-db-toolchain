output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint"
  value       = module.eks.cluster_endpoint
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "s3_bucket" {
  description = "S3 backup bucket name"
  value       = aws_s3_bucket.backups.bucket
}

output "irsa_role_arn" {
  description = "IAM role ARN for the db-toolchain ServiceAccount"
  value       = aws_iam_role.db_toolchain.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for the app image"
  value       = aws_ecr_repository.app.repository_url
}

output "kubeconfig_command" {
  description = "Configure kubectl for this cluster"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
