data "aws_vpc" "default" {
  count   = var.enable_observability_host ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.enable_observability_host ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

data "aws_ami" "amazon_linux" {
  count  = var.enable_observability_host ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-*-arm64"]
  }
}

resource "aws_security_group" "observability" {
  count       = var.enable_observability_host ? 1 : 0
  name        = "${var.name_prefix}-${var.environment}-observability"
  description = "Prometheus + Grafana for idp-db-toolchain"
  vpc_id      = data.aws_vpc.default[0].id

  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  ingress {
    description = "Prometheus UI"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project     = "idp-db-toolchain"
    Environment = var.environment
  }
}

resource "aws_instance" "observability" {
  count                  = var.enable_observability_host ? 1 : 0
  ami                    = data.aws_ami.amazon_linux[0].id
  instance_type          = var.observability_instance_type
  subnet_id              = tolist(data.aws_subnets.default[0].ids)[0]
  vpc_security_group_ids = [aws_security_group.observability[0].id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    grafana_admin_password = random_password.grafana_admin.result
    prometheus_config = templatefile("${path.module}/../../deploy/observability/prometheus.yml.tpl", {
      metrics_target = var.db_toolchain_metrics_target
      metrics_scheme = var.db_toolchain_metrics_scheme
    })
    prometheus_rules    = file("${path.module}/../../deploy/observability/prometheus-rules.yml")
    grafana_datasources = file("${path.module}/../../deploy/observability/grafana-datasources.yml")
    grafana_dashboards  = file("${path.module}/../../deploy/observability/grafana-dashboards.yml")
    grafana_dashboard   = file("${path.module}/../../deploy/observability/grafana-dashboard.json")
    docker_compose      = file("${path.module}/../../deploy/observability/docker-compose.yml")
  })

  tags = {
    Name        = "${var.name_prefix}-${var.environment}-observability"
    Project     = "idp-db-toolchain"
    Environment = var.environment
  }
}
