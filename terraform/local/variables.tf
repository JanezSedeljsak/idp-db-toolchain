variable "aws_region" {
  description = "AWS region (LocalStack default)"
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "LocalStack endpoint URL"
  type        = string
  default     = "http://localhost:30456"
}

variable "bucket_name" {
  description = "S3 bucket name for database backups"
  type        = string
  default     = "db-backups"
}
