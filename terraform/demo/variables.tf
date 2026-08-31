variable "aws_region" {
  description = "AWS region for the demo cluster"
  type        = string
  default     = "eu-central-1"
}

variable "name_prefix" {
  description = "Prefix for AWS resource names"
  type        = string
  default     = "idp-db-toolchain"
}

variable "cluster_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EKS managed node group instance type"
  type        = string
  default     = "t4g.medium"
}

variable "budget_limit_eur" {
  description = "Monthly cost budget alert threshold (EUR)"
  type        = number
  default     = 20
}

variable "budget_email" {
  description = "Email address for AWS Budget alerts (required)"
  type        = string
}

variable "k8s_namespace" {
  description = "Kubernetes namespace for db-toolchain"
  type        = string
  default     = "idp-db-toolchain"
}

variable "k8s_service_account" {
  description = "Kubernetes ServiceAccount name for IRSA"
  type        = string
  default     = "db-toolchain"
}
