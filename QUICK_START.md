# 🚀 adRouter 快速启动指南

## ✅ 环境变量问题已解决！

如果你遇到了 `ValueError: Missing required database environment variables` 错误，现在已经修复了！

## 📋 前置要求

- Python 3.11+
- MySQL 数据库

## 🔧 快速启动

### 方法1：使用启动脚本（推荐）

```bash
# 1. 配置数据库环境变量
cp .env.example .env  # 如果没有.env文件
nano .env             # 编辑数据库配置

# 2. 一键启动（自动处理虚拟环境）
./start_with_venv.sh
```

### 方法2：手动操作

```bash
# 1. 创建/激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cat > .env << 'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_db_user
MYSQL_PASSWORD=your_db_password
MYSQL_DB=ad_router
EOF

# 4. 启动应用
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔍 验证启动

启动成功后，访问以下地址验证：

- **健康检查**: http://localhost:8000/health
- **API文档**: http://localhost:8000/docs  
- **根路径**: http://localhost:8000/

健康检查应该返回：
```json
{
  "ok": true,
  "timestamp": 1734567890,
  "version": "1.0.0",
  "db_ok": true
}
```

## 🐛 问题排查

### Q: 仍然报环境变量错误？
A: 检查以下几点：
- 是否在虚拟环境中运行：`source .venv/bin/activate`
- .env文件是否在项目根目录
- .env文件格式是否正确（无空格，无引号）

### Q: 数据库连接失败？
A: 检查：
- MySQL服务是否启动
- 数据库用户权限是否正确
- 网络连接是否正常

### Q: 如何停止服务？
A: 在终端按 `Ctrl+C`

## 📁 .env文件格式

```bash
# 必需配置
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=ad_router

# 可选配置
# ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

## 🔒 安全提醒

- ✅ `.env`文件已在`.gitignore`中，不会被提交
- ✅ 生产环境请使用强密码
- ✅ 考虑使用专门的密钥管理服务

## 🎯 下一步

启动成功后，可以：
1. 查看API文档了解接口
2. 运行测试脚本验证功能
3. 配置上游和下游连接

## 💡 开发提示

```bash
# 进入虚拟环境
source .venv/bin/activate

# 运行测试
python test_fixes.py

# 查看日志
tail -f logs/app.log  # 如果有日志文件
```

现在可以正常使用了！🎉

