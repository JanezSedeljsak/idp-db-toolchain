module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = local.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnets

  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    demo = {
      instance_types = [var.node_instance_type]
      ami_type       = "AL2023_ARM_64_STANDARD"
      min_size       = 1
      max_size       = 1
      desired_size   = 1
      capacity_type  = "ON_DEMAND"
    }
  }

  tags = local.common_tags
}
