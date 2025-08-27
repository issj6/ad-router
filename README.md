# OCPX中转系统

一个高性能的广告追踪中转服务，为OCPX行业提供统一的上游/下游对接解决方案。

## 特性

- 🚀 **高性能**: 基于FastAPI异步框架，支持高并发
- 🔧 **模块化配置**: 多文件配置架构，易于维护和扩展
- 🛡️ **数据安全**: 支持签名验证，数据隔离
- 📊 **链路追踪**: 完整的请求链路追踪和日志记录
- 🔄 **自动重试**: 智能重试机制，提高成功率
- 📅 **数据管理**: MySQL数据库，高可靠性和性能

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置系统

系统使用多文件配置架构，配置文件位于 `config/` 目录：

```
config/
├── main.yaml           # 主配置文件（系统设置 + 路由规则）
├── upstreams/          # 上游配置目录
│   ├── adapi.yaml      # 微风互动配置
│   └── duokaiyou.yaml  # 多开游配置
└── downstreams/        # 下游配置目录（可选）
```

**主配置文件示例** (`config/main.yaml`):
```yaml
settings:
  callback_base: "https://your-domain.com"  # 修改为你的域名
  timezone: "Asia/Shanghai"
  app_secret: "your_random_secret_key"      # 修改为随机密钥

upstream_configs:
  - id: "adapi"
    name: "微风互动"
    source: "local"
    path: "upstreams/adapi.yaml"
    required: true
    enabled: true

routes:
  - match_key: "ad_id"
    rules:
      - equals: "67576"
        upstream: "adapi"
        enabled: true
        throttle: 0.2
```

详细配置说明请查看：[config/README.md](config/README.md)

### 3. 启动服务

```bash
# 使用默认配置目录 ./config
python start.py

# 或指定配置目录
CONFIG_DIR=./config python start.py

# 开发模式（热重载）
python start.py --reload

# 生产模式
python start.py --production --workers 4
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:6789/health

# API文档
# 浏览器访问: http://localhost:6789/docs
```

## 配置管理

### 验证配置
```bash
python tools/config_manager.py validate ./config
```

### 添加新上游
```bash
python tools/config_manager.py add-upstream ./config new_upstream_id --name "新上游名称"
```

### 列出所有上游
```bash
python tools/config_manager.py list ./config
```

### 从单文件迁移（如果需要）
```bash
python tools/config_manager.py split old_config.yaml ./config
```

## 接口文档

### 下游对接

详细的下游对接文档请查看：[docs/downstream_api.md](docs/downstream_api.md)

**主要接口**：
- `GET /v1/track` - 统一上报接口（支持click/imp/event）

**示例请求**：
```bash
curl "http://localhost:6789/v1/track?event_type=click&ds_id=your_downstream_id&ad_id=67576&callback=https%3A%2F%2Fyour-domain.com%2Fcallback%3Fevent%3D__EVENT_TYPE__%26amount%3D__AMOUNT__"
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
│   ├── config.py          # 多文件配置加载器
│   ├── db.py              # 数据库管理
│   ├── models.py          # 数据模型
│   ├── schemas.py         # API模型
│   ├── mapping_dsl.py     # DSL解释器
│   └── main.py            # 应用入口
├── config/                # 配置目录
│   ├── main.yaml          # 主配置文件
│   ├── upstreams/         # 上游配置目录
│   ├── downstreams/       # 下游配置目录
│   └── README.md          # 配置说明
├── tools/                 # 配置管理工具
│   └── config_manager.py  # 配置管理命令行工具
├── docs/                  # 文档
│   ├── downstream_api.md  # 下游对接文档
│   └── tutorial.md        # 配置教程
├── requirements.txt       # 依赖列表
├── start.py              # 启动脚本
└── README.md             # 项目说明
```

## 配置示例

### 上游配置 (`config/upstreams/example.yaml`)

```yaml
id: "example_upstream"
name: "示例上游"
description: "示例上游广告平台"
secrets:
  secret: "upstream_secret_key"
adapters:
  outbound:
    click:
      method: "GET"
      url: "https://api.example.com/click?aid={{aid}}&ts={{ts}}&callback={{callback}}&sig={{sig}}"
      macros:
        aid: "udm.ad.ad_id | url_encode()"
        ts: "udm.time.ts"
        callback: "cb_url() | url_encode()"
        sig: "hmac_sha256(secret_ref('secret'), join('&',[aid,ts]))"
      timeout_ms: 3000
      retry: {max: 2, backoff_ms: 500}
  inbound_callback:
    event:
      source: "query"
      field_map:
        "udm.event.type": "const:event"
        "udm.event.name": "query.event_type"
        "udm.time.ts": "now_ms()"
```

### 路由配置 (`config/main.yaml`)

```yaml
routes:
  - match_key: "ad_id"
    rules:
      - equals: "67576"
        upstream: "example_upstream"
        enabled: true
        throttle: 0.2  # 扣量20%
    fallback_upstream: ""
    fallback_enabled: false
```

## 环境变量配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `CONFIG_DIR` | 配置目录路径 | `./config` |
| `MAIN_CONFIG_URL` | 远程主配置URL | `https://example.com/config/main.yaml` |

## 生产部署

### 使用内置启动脚本（推荐）

```bash
# 生产模式，4个工作进程
python start.py --production --workers 4 --host 0.0.0.0 --port 6789
```

### 直接使用Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:6789
```

### 使用Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 6789

# 设置配置目录
ENV CONFIG_DIR=/app/config

CMD ["python", "start.py", "--production", "--workers", "4", "--host", "0.0.0.0", "--port", "6789"]
```

## 监控与维护

### 数据库管理

系统使用MySQL数据库，可通过标准MySQL客户端或管理工具进行管理：

```bash
# 连接数据库（需要设置环境变量）
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB

# 事件统计示例
SELECT ds_id, event_type, COUNT(*) FROM request_log GROUP BY ds_id, event_type;
```

环境变量配置：
```bash
export MYSQL_HOST=your_mysql_host
export MYSQL_USER=your_mysql_user  
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DB=your_mysql_database
```

### 日志监控

系统提供详细的结构化日志，每个请求都有唯一的 `trace_id` 用于链路追踪。

### 配置热更新

```bash
# 验证新配置
python tools/config_manager.py validate ./config

# 重启服务应用新配置
./restart.sh
```

## 技术栈

- **Web框架**: FastAPI
- **数据库**: MySQL (异步连接池)
- **ORM**: SQLAlchemy 2.0 (异步)
- **HTTP客户端**: httpx
- **配置格式**: YAML (多文件架构)
- **Python版本**: 3.11+

## 常见问题

### Q: 如何添加新的上游？
A: 使用配置管理工具：`python tools/config_manager.py add-upstream ./config new_upstream_id --name "新上游"`

### Q: 如何修改路由规则？
A: 编辑 `config/main.yaml` 中的 `routes` 部分，然后重启服务。

### Q: 配置文件格式错误怎么办？
A: 使用验证工具：`python tools/config_manager.py validate ./config`

### Q: 如何从旧版本迁移？
A: 如果有单文件配置，使用：`python tools/config_manager.py split old_config.yaml ./config`

## 贡献

欢迎提交Issue和Pull Request来改进项目。

## 许可证

MIT License

## 联系方式

如有问题请联系技术支持团队。