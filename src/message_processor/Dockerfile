FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY main.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV KAFKA_TOPIC=messages

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "main.py"]
