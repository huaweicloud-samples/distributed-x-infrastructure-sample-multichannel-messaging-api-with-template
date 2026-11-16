# ============================================================================
# 多渠道消息 API - 华为云 Terraform IaC (简化版)
# ============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = "~> 1.70"
    }
  }
}

provider "huaweicloud" {
  region = var.region
}

variable "region" {
  description = "华为云区域"
  type        = string
  default     = "cn-east-3"
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "multichannel-messaging"
}

# ============================================================================
# Layer 1: 基础设施与网络
# ============================================================================

resource "huaweicloud_vpc" "main" {
  name                  = "${var.project_name}-vpc"
  cidr                  = "10.0.0.0/16"
}

resource "huaweicloud_vpc_subnet" "main" {
  name       = "${var.project_name}-subnet"
  vpc_id     = huaweicloud_vpc.main.id
  cidr       = "10.0.1.0/24"
  gateway_ip = "10.0.1.1"
}

resource "huaweicloud_networking_secgroup" "main" {
  name        = "${var.project_name}-sg"
  description = "Security group for messaging API"
}

resource "huaweicloud_networking_secgroup_rule" "allow_http" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix = "0.0.0.0/0"
  security_group_id = huaweicloud_networking_secgroup.main.id
}

resource "huaweicloud_networking_secgroup_rule" "allow_https" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix = "0.0.0.0/0"
  security_group_id = huaweicloud_networking_secgroup.main.id
}

# ============================================================================
# Layer 2: RDS MySQL (替换 GeminiDB)
# ============================================================================

resource "huaweicloud_rds_instance" "templates" {
  name              = "${var.project_name}-mysql"
  flavor            = "rds.mysql.s6.large.2"
  security_group_id = huaweicloud_networking_secgroup.main.id
  subnet_id         = huaweicloud_vpc_subnet.main.id
  vpc_id            = huaweicloud_vpc.main.id

  db {
    type = "MySQL"
    version = "8.0"
    password = var.geminidb_password
    port = 3306
  }

  volume {
    type = "ULTRAHIGH"
    size = 100
  }

  availability_zone = ["cn-east-3a"]

  tags = {
    project = var.project_name
  }
}

variable "geminidb_password" {
  description = "GeminiDB 密码"
  type        = string
  sensitive   = true
  default     = "TempPass123!"
}

# ============================================================================
# Layer 3: DMS Kafka
# ============================================================================

resource "huaweicloud_dms_kafka_instance" "main" {
  name              = "${var.project_name}-kafka"
  engine_version    = "2.7"
  storage_spec_code = "dms.physical.storage.ultra.v2"
  flavor_id         = "c6.2u4g.cluster"
  broker_num        = 3
  storage_space     = 600
  vpc_id            = huaweicloud_vpc.main.id
  network_id        = huaweicloud_vpc_subnet.main.id
  security_group_id = huaweicloud_networking_secgroup.main.id
  availability_zones   = ["cn-east-3a", "cn-east-3b", "cn-east-3c"]

  tags = {
    project = var.project_name
  }
}

resource "huaweicloud_dms_kafka_topic" "messages" {
  instance_id = huaweicloud_dms_kafka_instance.main.id
  name        = "messages"
  partitions  = 12
  replicas    = 3
}

# ============================================================================
# Layer 4: APIG
# ============================================================================

resource "huaweicloud_apig_instance" "main" {
  name              = "${var.project_name}-apig"
  edition           = "BASIC"
  vpc_id            = huaweicloud_vpc.main.id
  subnet_id         = huaweicloud_vpc_subnet.main.id
  security_group_id = huaweicloud_networking_secgroup.main.id

  tags = {
    project = var.project_name
  }
}

resource "huaweicloud_apig_group" "main" {
  name        = "${var.project_name}-api-group"
  instance_id = huaweicloud_apig_instance.main.id
  description = "API group for messaging API"
}

# ============================================================================
# 输出
# ============================================================================

output "apig_endpoint" {
  description = "APIG API endpoint URL"
  value       = "https://${huaweicloud_apig_instance.main.ingress_address}/"
}

output "rds_endpoint" {
  description = "RDS MySQL endpoint"
  value       = huaweicloud_rds_instance.templates.private_ips[0]
}

output "vpc_id" {
  description = "VPC ID"
  value       = huaweicloud_vpc.main.id
}

output "subnet_id" {
  description = "Subnet ID"
  value       = huaweicloud_vpc_subnet.main.id
}
