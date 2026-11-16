# 部署指南

> 多渠道消息 API 华为云部署指南

## 前置条件

### 1. 华为云账号准备

- 已注册华为云账号
- 已完成实名认证
- 账号余额充足

### 2. 环境准备

- 安装华为云 CLI (`huaweicloud-cli`)
- 安装 Terraform (>= 1.5)
- 安装 Docker
- 配置 kubectl 访问 CCE

### 3. 权限要求

部署需要以下权限：
- VPC 管理权限
- CCE 集群管理权限
- DMS Kafka 管理权限
- GeminiDB 管理权限
- APIG 管理权限
- KMS 管理权限
- CSMS 管理权限
- SMN 管理权限
- CES 管理权限

## 部署步骤

### 步骤 1: 配置华为云凭据

```bash
# 设置环境变量
export HW_ACCESS_KEY="your-access-key"
export HW_SECRET_KEY="your-secret-key"
export HW_REGION="cn-north-4"
```

### 步骤 2: 初始化 Terraform

```bash
cd infra

# 复制变量文件
cp terraform.tfvars.example terraform.tfvars

# 编辑变量文件，配置实际值
# - jwt_secret: JWT 认证密钥
# - geminidb_password: GeminiDB 密码
# - smtp_password: SMTP 密码 (可选)
```

### 步骤 3: 部署基础设施

```bash
# 初始化 Terraform
terraform init

# 预览部署
terraform plan

# 执行部署
terraform apply
```

### 步骤 4: 构建并推送容器镜像

```bash
# 构建镜像
cd ../src/message_processor
docker build -t message-processor:latest .

# 推送到 SWR
docker tag message-processor:latest swr.cn-north-4.myhuaweicloud.com/multichannel-messaging/message-processor:latest
docker push swr.cn-north-4.myhuaweicloud.com/multichannel-messaging/message-processor:latest
```

### 步骤 5: 部署 CCE 容器

CCE 容器需要通过 kubectl 或 CCE 控制台部署：

```yaml
# message-processor-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: message-processor
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: message-processor
  template:
    metadata:
      labels:
        app: message-processor
    spec:
      containers:
      - name: message-processor
        image: swr.cn-north-4.myhuaweicloud.com/multichannel-messaging/message-processor:latest
        ports:
        - containerPort: 8080
        env:
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "<从 terraform output 获取>"
        - name: KAFKA_TOPIC
          value: "messages"
        - name: GEMINIDB_ENDPOINT
          value: "<从 terraform output 获取>"
        - name: GEMINIDB_PASSWORD
          value: "<数据库密码>"
        - name: SMTP_HOST
          value: "<SMTP 服务器>"
        - name: SMTP_USER
          value: "<SMTP 用户名>"
        - name: SMTP_PASSWORD
          value: "<SMTP 密码>"
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "1000m"
            memory: "1Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: message-processor
  namespace: default
spec:
  selector:
    app: message-processor
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
```

部署:
```bash
kubectl apply -f message-processor-deployment.yaml
```

### 步骤 5: 配置模板数据

连接 GeminiDB 并创建模板表：

```sql
CREATE DATABASE IF NOT EXISTS messaging;
USE messaging;

CREATE TABLE IF NOT EXISTS message_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(255) NOT NULL,
    channel_type VARCHAR(50) NOT NULL,
    subject VARCHAR(500),
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_template_channel (template_name, channel_type)
);

-- 插入示例模板
INSERT INTO message_templates (template_name, channel_type, subject, body) VALUES
('alert-template', 'EMAIL', '账户余额提醒', '<p>您的 {productName} 账户（尾号 {membershipNumber}）余额为 ${accountBalance}。</p>'),
('alert-template', 'SMS', '', '提醒：您的 {productName} 账户（尾号 {membershipNumber}）余额为 ${accountBalance}');
```

### 步骤 6: 验证部署

```bash
# 获取 APIG 端点
APIG_ENDPOINT=$(terraform output -raw apig_endpoint)
echo "API Endpoint: $APIG_ENDPOINT"

# 发送测试请求
curl -X POST "$APIG_ENDPOINT" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -d '{
    "EmailMessage": {
      "FromAddress": "alerts@example.com",
      "Subject": "测试邮件",
      "MessageBody": "<p>这是一封测试邮件</p>"
    },
    "Addresses": {
      "test@example.com": {
        "ChannelType": "EMAIL"
      }
    }
  }'
```

## 配置说明

### 消息队列 (DMS Kafka)

- 主题：`messages` - 主消息队列
- 主题：`messages-dlq` - 死信队列
- 分区数：12
- 副本数：3

### 模板存储 (GeminiDB)

- 模式：DynamoDB 兼容
- 节点数：3
- 存储空间：100GB

### 容器集群 (CCE)

- 节点数：2
- 节点规格：s6.large.2
- Kubernetes 版本：v1.28

## 清理资源

```bash
# 销毁所有资源
terraform destroy
```

## 常见问题

### 1. Kafka 连接失败

检查：
- DMS Kafka 实例状态是否为 "Running"
- 安全组是否放行了 9092/9093 端口
- VPC 子网是否正确配置

### 2. GeminiDB 连接失败

检查：
- GeminiDB 实例状态是否为 "Running"
- 安全组是否放行了 3306 端口
- 凭据是否正确

### 3. 容器部署失败

检查：
- 镜像是否成功推送到 SWR
- CCE 节点是否 Ready
- 容器镜像地址是否正确
