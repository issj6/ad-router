#!/bin/bash

# 卡普卡 Docker 一键部署脚本
# 使用方法：chmod +x deploy.sh && ./deploy.sh

set -e

echo "🚀 开始部署卡普卡广告路由系统..."

# 检查 Docker 和 Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

# 检查必要文件
required_files=("config.yaml" "requirements.txt")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ 缺少必要文件: $file"
        exit 1
    fi
done

# 创建日志目录
mkdir -p logs

# 检查 MySQL 连接配置
echo "🔍 检查 MySQL 连接配置..."
MYSQL_HOST=${MYSQL_HOST:-"127.0.0.1"}
MYSQL_PORT=${MYSQL_PORT:-"3306"}
MYSQL_USER=${MYSQL_USER:-"root"}
MYSQL_PASSWORD=${MYSQL_PASSWORD:-"123456"}
MYSQL_DB=${MYSQL_DB:-"ad_router"}

echo "MySQL 配置："
echo "  主机: $MYSQL_HOST"
echo "  端口: $MYSQL_PORT"
echo "  用户: $MYSQL_USER"
echo "  数据库: $MYSQL_DB"
echo ""
echo "⚠️  请确保 MySQL 服务已启动且数据库 '$MYSQL_DB' 已创建"
read -p "是否继续部署？(y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 部署已取消"
    exit 1
fi

# 停止并删除旧容器（如果存在）
echo "🛑 停止旧容器..."
docker compose down --remove-orphans || true

# 清理旧镜像（可选）
read -p "是否清理旧的应用镜像？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 清理旧镜像..."
    docker rmi adrouter-adrouter:latest 2>/dev/null || true
fi

# 构建并启动服务
echo "🔨 构建并启动服务..."
docker compose up -d --build

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "🔍 检查服务状态..."
docker compose ps

# 检查健康状态
echo "🏥 检查应用健康状态..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if curl -f http://localhost:6789/health &> /dev/null; then
        echo "✅ 应用启动成功！"
        break
    else
        echo "⏳ 等待应用启动... ($attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    fi
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ 应用启动超时，请检查日志"
    echo "查看应用日志: docker compose logs adrouter"
    echo "查看数据库日志: docker compose logs mysql"
    exit 1
fi

# 显示部署信息
echo ""
echo "🎉 部署完成！"
echo ""
echo "📋 服务信息："
echo "  - 应用地址: http://localhost:6789"
echo "  - 健康检查: http://localhost:6789/health"
echo "  - MySQL 连接: $MYSQL_HOST:$MYSQL_PORT"
echo ""
echo "📝 常用命令："
echo "  - 查看日志: docker compose logs -f adrouter"
echo "  - 重启服务: docker compose restart adrouter"
echo "  - 停止服务: docker compose down"
echo "  - 进入容器: docker compose exec adrouter bash"
echo ""
echo "🧪 测试接口："
echo "  curl 'http://localhost:6789/v1/track?ds_id=test&event_type=click&ad_id=123&click_id=test123'"
echo ""

# 显示健康检查结果
echo "🏥 当前健康状态："
curl -s http://localhost:6789/health | python3 -m json.tool 2>/dev/null || echo "无法获取健康状态"
