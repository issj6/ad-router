# 部署指南 - adRouter优化版本

## 🔧 优化内容总结

1. **安全性增强**
   - ✅ 移除硬编码数据库密码，改为环境变量
   - ✅ 数据库连接验证，启动时检查配置

2. **Bug修复**
   - ✅ 修复HealthResponse重复定义
   - ✅ 修复幂等性处理中的变量引用错误
   - ✅ 完善异常处理，添加具体日志

3. **架构验证**
   - ✅ 确认上下游完全通过配置文件管理
   - ✅ 验证上下游相互屏蔽的设计

## 📋 部署前准备

### 1. 设置环境变量

创建 `.env` 文件或设置系统环境变量：

```bash
# 必需的数据库配置
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_db_user
export MYSQL_PASSWORD=your_db_password
export MYSQL_DB=ad_router

# 可选的CORS配置
# export ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### 2. 验证配置文件

确保 `config/main.yaml` 包含正确的配置：
- 检查 `callback_base` 是否为你的域名
- 验证 `app_secret` 已更改为随机密钥
- 确认上游配置文件存在于 `config/upstreams/` 目录
- 确认所有上游配置正确

## 🚀 部署步骤

### 开发环境

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量
source .env  # 或使用其他方式设置

# 3. 启动服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 生产环境（Docker）

```bash
# 1. 构建镜像
docker build -t adrouter:latest .

# 2. 运行容器（使用环境变量文件）
docker run -d \
  --name adrouter \
  --env-file .env \
  -p 6789:6789 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  adrouter:latest
```

### 生产环境（Docker Compose）

```bash
# 1. 创建 .env 文件
cp .env.example .env
# 编辑 .env 填入实际的数据库配置

# 2. 启动服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

## ✅ 验证部署

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{
  "ok": true,
  "timestamp": 1234567890,
  "version": "1.0.0",
  "db_ok": true
}
```

### 2. API文档

浏览器访问：http://localhost:8000/docs

### 3. 测试完整流程

```bash
# 测试点击上报
curl -X GET "http://localhost:8000/v1/track?ds_id=test&event_type=click&ad_id=test_ad&click_id=test_click"
```

## ⚠️ 注意事项

1. **环境变量**：生产环境必须设置所有必需的环境变量，否则服务将无法启动
2. **数据库连接**：确保数据库服务可访问，并且用户有相应权限
3. **配置验证**：部署后立即进行健康检查，确保数据库连接正常
4. **日志监控**：关注启动日志，确保没有配置错误

## 🔄 回滚方案

如果新版本出现问题：

1. 停止当前服务
2. 切换到之前的代码版本
3. 使用旧的部署方式（包含硬编码的数据库配置）
4. 重新启动服务

## 📞 故障排查

### 服务无法启动
- 检查环境变量是否正确设置
- 查看错误日志：`ValueError: Missing required database environment variables`

### 数据库连接失败
- 验证数据库服务是否运行
- 检查网络连接和防火墙设置
- 确认数据库用户权限

### API报错
- 查看详细日志，现在包含更多调试信息
- 检查 config/main.yaml 配置是否正确
