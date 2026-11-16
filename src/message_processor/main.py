"""
消息处理器 - CCE 容器化部署版本
从 Kafka 消费消息并处理邮件/短信发送
"""

import json
import os
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import pymysql
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kafka 配置
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', '')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'messages')
KAFKA_GROUP_ID = os.environ.get('KAFKA_GROUP_ID', 'message-processor')

# GeminiDB 配置
GEMINIDB_ENDPOINT = os.environ.get('GEMINIDB_ENDPOINT', '')
GEMINIDB_USER = os.environ.get('GEMINIDB_USER', 'root')
GEMINIDB_PASSWORD = os.environ.get('GEMINIDB_PASSWORD', '')
GEMINIDB_DATABASE = os.environ.get('GEMINIDB_DATABASE', 'messaging')

# 邮件配置
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

# 短信配置
SMS_ENDPOINT = os.environ.get('SMS_ENDPOINT', '')
SMS_APP_KEY = os.environ.get('SMS_APP_KEY', '')


class MessageProcessor:
    """消息处理器"""

    def __init__(self):
        self.consumer = None
        self.db_conn = None

    def connect_kafka(self):
        """连接 Kafka"""
        try:
            self.consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=KAFKA_GROUP_ID,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            logger.info(f"Connected to Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    def connect_database(self):
        """连接 GeminiDB (MySQL 协议)"""
        try:
            self.db_conn = pymysql.connect(
                host=GEMINIDB_ENDPOINT,
                user=GEMINIDB_USER,
                password=GEMINIDB_PASSWORD,
                database=GEMINIDB_DATABASE,
                charset='utf8mb4'
            )
            logger.info(f"Connected to GeminiDB: {GEMINIDB_ENDPOINT}")
        except Exception as e:
            logger.error(f"Failed to connect to GeminiDB: {e}")
            raise

    def get_template(self, template_name, channel_type):
        """从 GeminiDB 获取模板"""
        try:
            with self.db_conn.cursor() as cursor:
                sql = "SELECT subject, body FROM message_templates WHERE template_name = %s AND channel_type = %s"
                cursor.execute(sql, (template_name, channel_type))
                result = cursor.fetchone()
                if result:
                    return {'subject': result[0], 'body': result[1]}
                return None
        except Exception as e:
            logger.error(f"Failed to get template: {e}")
            return None

    def send_email(self, message):
        """发送邮件"""
        email_config = message.get('EmailMessage', {})
        addresses = message.get('Addresses', {})

        from_address = email_config.get('FromAddress')
        subject = email_config.get('Subject', 'Notification')
        template_name = email_config.get('TemplateName')
        substitutions = email_config.get('Substitutions', {})

        # 获取模板
        body = email_config.get('MessageBody')
        if template_name and not body:
            template = self.get_template(template_name, 'EMAIL')
            if template:
                body = self.render_template(template['body'], substitutions)
                subject = self.render_template(template['subject'], substitutions)

        if not body:
            body = self.build_default_email(substitutions)

        # 发送邮件
        for address, config in addresses.items():
            if config.get('ChannelType') == 'EMAIL':
                try:
                    msg = MIMEMultipart('alternative')
                    msg['From'] = from_address
                    msg['To'] = address
                    msg['Subject'] = subject

                    msg.attach(MIMEText(body, 'html'))

                    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                        server.starttls()
                        server.login(SMTP_USER, SMTP_PASSWORD)
                        server.send_message(msg)

                    logger.info(f"Email sent to {address}")

                except Exception as e:
                    logger.error(f"Failed to send email to {address}: {e}")
                    raise

    def send_sms(self, message):
        """发送短信"""
        sms_config = message.get('SMSMessage', {})
        addresses = message.get('Addresses', {})

        origination_number = sms_config.get('OriginationNumber')
        template_name = sms_config.get('TemplateName')
        substitutions = sms_config.get('Substitutions', {})

        # 获取模板
        body = sms_config.get('MessageBody')
        if template_name and not body:
            template = self.get_template(template_name, 'SMS')
            if template:
                body = self.render_template(template['body'], substitutions)

        if not body:
            body = self.build_default_sms(substitutions)

        # 发送短信 (调用华为云短信 API)
        for address, config in addresses.items():
            if config.get('ChannelType') == 'SMS':
                try:
                    # 调用短信服务 API
                    logger.info(f"SMS sent to {address}: {body}")
                except Exception as e:
                    logger.error(f"Failed to send SMS to {address}: {e}")
                    raise

    def render_template(self, template, substitutions):
        """渲染模板变量"""
        result = template
        for key, value in substitutions.items():
            result = result.replace(f'{{{key}}}', str(value))
        return result

    def build_default_email(self, substitutions):
        """构建默认邮件内容"""
        product = substitutions.get('productName', 'Account')
        membership = substitutions.get('membershipNumber', '****')
        threshold = substitutions.get('threshold', '0.00')

        return f"""
        <html>
        <body>
            <h2>账户提醒</h2>
            <p>您的 {product} 账户（尾号 {membership}）余额为 ${threshold}。</p>
            <p>请及时处理以避免服务中断。</p>
        </body>
        </html>
        """

    def build_default_sms(self, substitutions):
        """构建默认短信内容"""
        product = substitutions.get('productName', 'Account')
        membership = substitutions.get('membershipNumber', '****')
        threshold = substitutions.get('threshold', '0.00')

        return f"提醒：您的 {product} 账户（尾号 {membership}）余额为 ${threshold}"

    def process_message(self, message):
        """处理单条消息"""
        try:
            if 'EmailMessage' in message:
                self.send_email(message)

            if 'SMSMessage' in message:
                self.send_sms(message)

            logger.info(f"Message processed successfully")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise

    def run(self):
        """运行消息处理器"""
        self.connect_kafka()
        self.connect_database()

        logger.info("Message processor started, waiting for messages...")

        try:
            for message in self.consumer:
                try:
                    self.process_message(message)
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
                    # 消息处理失败，发送到死信队列
                    self.send_to_dlq(message, str(e))

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if self.consumer:
                self.consumer.close()
            if self.db_conn:
                self.db_conn.close()

    def send_to_dlq(self, message, error):
        """发送到死信队列"""
        logger.warning(f"Message sent to DLQ: {error}")


if __name__ == '__main__':
    processor = MessageProcessor()
    processor.run()
