output "s3_bucket" {
  description = "S3 bucket for database backups"
  value       = aws_s3_bucket.backups.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the backup bucket"
  value       = aws_s3_bucket.backups.arn
}

output "db_toolchain_irsa_role_arn" {
  description = "IAM role ARN - set on k8s/deploy/serviceaccount.yaml (eks.amazonaws.com/role-arn)"
  value       = aws_iam_role.db_toolchain.arn
}

output "grafana_url" {
  description = "Grafana URL (restrict admin_cidr in production)"
  value       = var.enable_observability_host ? "http://${aws_instance.observability[0].public_ip}:3000" : null
}

output "prometheus_url" {
  description = "Prometheus UI URL"
  value       = var.enable_observability_host ? "http://${aws_instance.observability[0].public_ip}:9090" : null
}

output "grafana_admin_password" {
  description = "Grafana admin password (change after first login)"
  value       = var.enable_observability_host ? random_password.grafana_admin.result : null
  sensitive   = true
}

output "prometheus_alerts_url" {
  description = "Firing alerts"
  value       = var.enable_observability_host ? "http://${aws_instance.observability[0].public_ip}:9090/alerts" : null
}

output "k8s_config_snippet" {
  description = "Values to patch into k8s/deploy/db-toolchain-config.yaml"
  value = {
    s3_bucket = aws_s3_bucket.backups.bucket
    s3_region = var.aws_region
    irsa_arn  = aws_iam_role.db_toolchain.arn
  }
}
