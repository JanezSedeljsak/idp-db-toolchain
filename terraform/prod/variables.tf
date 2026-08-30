variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment name (prod, staging, …)"
  type        = string
  default     = "prod"
}

variable "name_prefix" {
  description = "Prefix for AWS resource names"
  type        = string
  default     = "idp-db-backupper"
}

variable "eks_cluster_name" {
  description = "Existing EKS cluster where the backupper workload runs"
  type        = string
}

variable "k8s_namespace" {
  description = "Kubernetes namespace for the backupper ServiceAccount"
  type        = string
  default     = "idp-db-backupper"
}

variable "k8s_service_account" {
  description = "Kubernetes ServiceAccount name for IRSA"
  type        = string
  default     = "backupper"
}

variable "backupper_metrics_target" {
  description = "host:port scraped by Prometheus (internal LB, in-cluster IP, or VPN-reachable endpoint)"
  type        = string
}

variable "backupper_metrics_scheme" {
  description = "http or https for backupper metrics scrape"
  type        = string
  default     = "http"
}

variable "admin_cidr" {
  description = "CIDR allowed to reach Grafana (:3000) and Prometheus UI (:9090)"
  type        = string
}

variable "observability_instance_type" {
  description = "EC2 instance type for Prometheus + Grafana"
  type        = string
  default     = "t4g.small"
}

variable "enable_observability_host" {
  description = "Provision a small EC2 host running Prometheus + Grafana"
  type        = bool
  default     = true
}
