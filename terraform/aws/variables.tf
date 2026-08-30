variable "aws_region" {
  description = "AWS region for the demo stack"
  type        = string
  default     = "eu-central-1"
}

variable "name_prefix" {
  description = "Prefix for AWS resource names"
  type        = string
  default     = "idp-db-backupper"
}

variable "instance_type" {
  description = "EC2 instance type (ARM Graviton recommended)"
  type        = string
  default     = "t4g.small"
}

variable "ssh_cidr" {
  description = "CIDR allowed to SSH to the demo host"
  type        = string
  default     = "0.0.0.0/0"
}

variable "admin_cidr" {
  description = "CIDR allowed to reach backupper metrics on :8080"
  type        = string
  default     = "0.0.0.0/0"
}

variable "repo_url" {
  description = "Git URL cloned on first boot to run docker compose"
  type        = string
  default     = "https://github.com/JanezSedeljsak/idp-db-backupper.git"
}

variable "repo_ref" {
  description = "Git ref checked out on first boot"
  type        = string
  default     = "main"
}
