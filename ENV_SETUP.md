# 环境变量配置指南

## 🔧 修复"Missing required database environment variables"错误

如果遇到这个错误，说明系统无法读取到必需的数据库环境变量。

## 📋 必需的环境变量

- `MYSQL_HOST` - 数据库主机地址
- `MYSQL_PORT` - 数据库端口（默认3306）
- `MYSQL_USER` - 数据库用户名
- `MYSQL_PASSWORD` - 数据库密码
- `MYSQL_DB` - 数据库名称

## 🛠️ 配置方法

### 方法1：使用.env文件（推荐）

1. **创建.env文件**：
```bash
# 在项目根目录创建.env文件
cat > .env << 'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_db_user
MYSQL_PASSWORD=your_db_password
MYSQL_DB=ad_router
EOF
```

2. **修改为实际配置**：
```bash
# 编辑.env文件，填入真实的数据库信息
nano .env
```

3. **重启应用**：
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 方法2：导出环境变量

```bash
# 临时设置（仅当前会话有效）
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_db_user
export MYSQL_PASSWORD=your_db_password
export MYSQL_DB=ad_router

# 启动应用
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 方法3：使用Docker环境变量

```bash
# 使用.env文件启动Docker
docker run --env-file .env -p 8000:8000 adrouter:latest

# 或者直接设置环境变量
docker run \
  -e MYSQL_HOST=127.0.0.1 \
  -e MYSQL_USER=your_user \
  -e MYSQL_PASSWORD=your_password \
  -e MYSQL_DB=ad_router \
  -p 8000:8000 \
  adrouter:latest
```

### 方法4：Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  adrouter:
    build: .
    env_file:
      - .env  # 自动读取.env文件
    ports:
      - "8000:8000"
```

## ✅ 验证配置

配置完成后，启动应用验证：

```bash
# 启动应用
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 测试健康检查
curl http://localhost:8000/health
```

如果配置正确，应该看到类似以下响应：
```json
{
  "ok": true,
  "timestamp": 1734567890,
  "version": "1.0.0",
  "db_ok": true
}
```

## 🔒 安全注意事项

1. **不要提交.env文件到版本控制**：
```bash
# 确保.env文件在.gitignore中
echo ".env" >> .gitignore
```

2. **生产环境建议**：
   - 使用专门的密钥管理服务
   - 通过CI/CD系统注入环境变量
   - 使用Docker secrets或Kubernetes secrets

## 🐛 常见问题

### Q: 创建了.env文件但仍然报错？
A: 检查以下几点：
- .env文件是否在项目根目录
- 文件格式是否正确（无BOM，UTF-8编码）
- 变量名是否拼写正确
- 是否重启了应用

### Q: .env文件格式要求？
A: 
```bash
# ✅ 正确格式
MYSQL_HOST=127.0.0.1
MYSQL_USER=root

# ❌ 错误格式
MYSQL_HOST = 127.0.0.1  # 不能有空格
MYSQL_USER='root'       # 不需要引号
```

### Q: 如何查看当前环境变量？
A:
```bash
# 查看特定变量
echo $MYSQL_HOST

# 查看所有MySQL相关变量
env | grep MYSQL
```

## 📝 .env文件模板

```bash
# 数据库配置（必需）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_db_user
MYSQL_PASSWORD=your_db_password
MYSQL_DB=ad_router

# CORS配置（可选）
# ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

复制上面的模板并修改为你的实际配置即可。

