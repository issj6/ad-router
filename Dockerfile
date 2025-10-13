# 使用官方 Python 3.11 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 默认日志配置 - 生产环境关闭日志获得最佳性能
ENV ENABLE_LOGGING=false
ENV LOG_LEVEL=INFO

# 配置阿里云Debian源
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 6789

# 启动命令 - 优化的gunicorn多进程模式（不使用preload确保进程独立）
CMD ["gunicorn", "app.main:app", \
     "-w", "17", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:6789", \
     "--max-requests", "5000", \
     "--max-requests-jitter", "500", \
     "--timeout", "30", \
     "--keep-alive", "5"]
