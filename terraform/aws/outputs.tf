output "instance_public_ip" {
  description = "Public IP of the demo EC2 host"
  value       = aws_instance.demo.public_ip
}

output "s3_bucket" {
  description = "S3 bucket for database backups"
  value       = aws_s3_bucket.backups.bucket
}

output "ssh_command" {
  description = "SSH into the demo host (Amazon Linux, user ec2-user)"
  value       = "ssh ec2-user@${aws_instance.demo.public_ip}"
}

output "metrics_url" {
  description = "Backupper health/metrics endpoint"
  value       = "http://${aws_instance.demo.public_ip}:8080/health"
}

output "postgres_password" {
  description = "Password for the demo Postgres user (shop/billing/analytics)"
  value       = random_password.postgres.result
  sensitive   = true
}

output "estimated_weekly_cost_usd" {
  description = "Rough weekly cost for this minimal stack (excluding data transfer)"
  value       = "~8-12 USD (t4g.small + 20GB gp3 + S3 pennies; destroy when done)"
}
