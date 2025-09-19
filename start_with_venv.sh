#!/bin/bash

# adRouter 虚拟环境启动脚本

echo "🚀 启动 adRouter 项目"
echo "=================="

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在，正在创建..."
    python3 -m venv .venv
    echo "✅ 虚拟环境创建完成"
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source .venv/bin/activate

# 检查并安装依赖
echo "📦 检查依赖..."
pip install -r requirements.txt

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "⚠️  .env文件不存在，请创建.env文件并配置数据库信息："
    echo ""
    cat << 'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_db_user
MYSQL_PASSWORD=your_db_password
MYSQL_DB=ad_router
EOF
    echo ""
    echo "创建后重新运行此脚本"
    exit 1
fi

# 验证环境变量
echo "🔍 验证环境变量..."
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
required_vars = ['MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DB']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    print(f'❌ 缺少环境变量: {missing}')
    print('请检查.env文件配置')
    exit(1)
else:
    print('✅ 环境变量配置正确')
    print(f'数据库: {os.getenv(\"MYSQL_USER\")}@{os.getenv(\"MYSQL_HOST\")}:{os.getenv(\"MYSQL_PORT\", \"3306\")}/{os.getenv(\"MYSQL_DB\")}')
"

if [ $? -ne 0 ]; then
    exit 1
fi

# 启动应用
echo ""
echo "🎯 启动应用..."
echo "访问地址: http://localhost:6789"
echo "API文档: http://localhost:6789/docs"
echo "健康检查: http://localhost:6789/health"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 6789 --reload

