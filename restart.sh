#!/bin/bash

# 一键重启 Docker 部署脚本
# 用法：
#   chmod +x restart.sh
#   ./restart.sh              # 仅重启
#   ./restart.sh --build      # 重建镜像并重启
#   ./restart.sh --pull       # 先拉取镜像再重启（适用于远程镜像）
#   ./restart.sh --build --pull

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

SERVICE="adrouter"
DO_BUILD=false
DO_PULL=false
HEALTH_URL=${HEALTH_URL:-"http://localhost:6789/health"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      DO_BUILD=true
      shift
      ;;
    --pull)
      DO_PULL=true
      shift
      ;;
    --service)
      SERVICE="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1"
      echo "用法: $0 [--build] [--pull] [--service 服务名]"
      exit 1
      ;;
  esac
done

echo "🚀 开始重启部署 (service=$SERVICE, build=$DO_BUILD, pull=$DO_PULL)"

# 基础检查
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ 未检测到 docker，请先安装 Docker"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "❌ 未检测到 docker compose，请先安装 Docker Compose"
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/docker-compose.yml" ]]; then
  echo "❌ 找不到 docker-compose.yml"
  exit 1
fi

mkdir -p "$PROJECT_DIR/logs"

echo "🛑 停止并清理旧容器..."
docker compose down --remove-orphans || true

if $DO_PULL; then
  echo "📥 拉取最新镜像..."
  docker compose pull "$SERVICE" || true
fi

if $DO_BUILD; then
  echo "🔨 重建镜像..."
  docker compose build "$SERVICE"
fi

echo "🚀 启动服务..."
docker compose up -d "$SERVICE"

echo "⏳ 等待服务健康检查: $HEALTH_URL"
max_attempts=30
attempt=1
until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
  if [[ $attempt -ge $max_attempts ]]; then
    echo "❌ 健康检查超时，查看日志：docker compose logs -f $SERVICE"
    exit 1
  fi
  echo "... 第 $attempt/$max_attempts 次检查"
  attempt=$((attempt+1))
  sleep 2
done

echo "✅ 重启成功！"
echo "- 健康检查: $HEALTH_URL"
echo "- 查看日志: docker compose logs -f $SERVICE"
echo "- 重新部署(重建镜像): $0 --build"





