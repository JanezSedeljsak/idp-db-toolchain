resource "aws_ecr_repository" "app" {
  name                 = "idp-db-toolchain"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}
