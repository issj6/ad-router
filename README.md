# OCPX中转系统

一个高性能的广告追踪中转服务，为OCPX行业提供统一的上游/下游对接解决方案。

## 特性

- 🚀 **高性能**: 基于FastAPI异步框架，支持高并发
- 🔧 **配置驱动**: 通过YAML配置文件即可接入新的上游/下游
- 🛡️ **数据安全**: 支持签名验证，数据隔离
- 📊 **链路追踪**: 完整的请求链路追踪和日志记录
- 🔄 **自动重试**: 智能重试机制，提高成功率
- 📅 **数据管理**: 每日滚动的SQLite数据库，便于管理

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置系统

编辑 `config.yaml` 文件，修改基础配置：

```yaml
settings:
  callback_base: "https://your-domain.com"  # 修改为你的域名
  app_secret: "your_random_secret_key"      # 修改为随机密钥
```

### 3. 启动服务

```bash
# 开发模式
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者
python app/main.py
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# API文档
# 浏览器访问: http://localhost:8000/docs
```

## 接口文档

### 下游对接

详细的下游对接文档请查看：[docs/downstream_api.md](docs/downstream_api.md)

**主要接口**：
- `POST /v1/track/click` - 点击上报
- `POST /v1/track/imp` - 曝光上报  
- `POST /v1/track/event` - 转化事件上报

**示例请求**：
```bash
curl -X POST "http://localhost:8000/v1/track/click" \
  -H "Content-Type: application/json" \
  -d '{
    "ds_id": "your_downstream_id",
    "event_type": "click",
    "campaign_id": "cmp_456",
    "click_id": "ck_abc123"
  }'
```

### 配置教程

完整的配置教程请查看：[docs/tutorial.md](docs/tutorial.md)

## 系统架构

```
下游媒体 → 统一API → 路由引擎 → 映射引擎 → 上游广告主
    ↑                                           ↓
    ← 回调映射 ← 回调处理 ← 回调验证 ← 上游回调
```

## 目录结构

```
adRouter/
├── app/                    # 应用代码
│   ├── routers/           # 路由模块
│   ├── services/          # 业务服务
│   ├── utils/             # 工具函数
│   ├── config.py          # 配置加载
│   ├── db.py              # 数据库管理
│   ├── models.py          # 数据模型
│   ├── schemas.py         # API模型
│   ├── mapping_dsl.py     # DSL解释器
│   └── main.py            # 应用入口
├── docs/                  # 文档
│   ├── downstream_api.md  # 下游对接文档
│   └── tutorial.md        # 配置教程
├── data/                  # 数据目录（自动创建）
│   └── sqlite/            # SQLite数据库文件
├── config.yaml            # 配置文件
├── requirements.txt       # 依赖列表
└── README.md             # 项目说明
```

## 配置示例

### 上游配置

```yaml
upstreams:
  - id: "upstream_a"
    secrets:
      secret: "upstream_secret"
    adapters:
      outbound:
        click:
          method: "GET"
          url: "https://api.upstream.com/click?aid={{aid}}&sig={{sig}}"
          macros:
            aid: "udm.ad.ad_id | url_encode()"
            sig: "hmac_sha256(secret_ref('secret'), aid)"
```

### 路由配置

```yaml
routes:
  - match_key: "campaign_id"
    rules:
      - equals: "cmp_123"
        upstream: "upstream_a"
        downstream: "downstream_b"
    fallback_upstream: "upstream_a"
    fallback_downstream: "downstream_b"
```

## 生产部署

### 使用Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 使用Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

## 监控与维护

### 数据库管理

```bash
# 查看今日数据
sqlite3 ./data/sqlite/$(date +%Y%m%d).db

# 事件统计
SELECT ds_id, event_type, COUNT(*) FROM event_log GROUP BY ds_id, event_type;
```

### 日志监控

系统提供详细的结构化日志，每个请求都有唯一的 `trace_id` 用于链路追踪。

## 技术栈

- **Web框架**: FastAPI
- **数据库**: SQLite (每日滚动)
- **ORM**: SQLAlchemy 2.0 (异步)
- **HTTP客户端**: httpx
- **配置格式**: YAML
- **Python版本**: 3.11+

## 贡献

欢迎提交Issue和Pull Request来改进项目。

## 许可证

MIT License

## 联系方式

如有问题请联系技术支持团队。
