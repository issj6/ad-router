# OCPX中转系统 - 项目总结与配置教程

## 项目概述

OCPX中转系统是一个高性能的广告追踪中转服务，作为中游角色连接上游广告主和下游媒体方。系统的核心价值在于：

1. **统一接口**：为所有下游提供统一的API接口，屏蔽上游差异
2. **配置驱动**：通过简单的YAML配置即可接入新的上游/下游，无需编码
3. **高性能**：基于FastAPI异步框架，支持高并发处理
4. **数据隔离**：MySQL数据库，高可靠性和性能保障
5. **链路追踪**：完整的请求链路追踪，便于问题排查

## 系统架构

```
下游媒体 → 统一API → 路由引擎 → 映射引擎 → 上游广告主
    ↑                                           ↓
    ← 回调映射 ← 回调处理 ← 回调验证 ← 上游回调
```

### 核心组件

- **统一API层**：提供标准化的上报接口（/v1/track/*）
- **路由引擎**：根据配置规则选择目标上游
- **映射引擎**：基于DSL配置进行字段映射和数据转换
- **回调处理**：处理上游回调并转发给下游
- **数据存储**：MySQL数据库，异步连接池

## 快速开始

### 1. 环境准备

```bash
# 克隆项目（如果从git获取）
# git clone <repository_url>
# cd adRouter

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置修改

编辑 `config.yaml` 文件：

```yaml
settings:
  callback_base: "https://cbkpk.notnull.cc"  # 修改为你的域名
  app_secret: "your_random_secret_key"       # 修改为随机密钥
```

### 3. 启动服务

```bash
# 开发模式启动
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者直接运行
python app/main.py
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 查看API文档
# 浏览器访问: http://localhost:8000/docs
```

## 配置详解

### 基础设置 (settings)

```yaml
settings:
  callback_base: "https://cbkpk.notnull.cc"  # 回调基础域名
  timezone: "Asia/Shanghai"                   # 时区设置

  app_secret: "CHANGE_ME_TO_RANDOM_SECRET"    # 用于token签名的密钥
```

### 上游配置 (upstreams)

```yaml
upstreams:
  - id: "upstream_a"                    # 上游唯一标识
    name: "上游A"                       # 上游名称（可选）
    secrets:                            # 上游相关密钥
      secret: "upstream_a_secret"
      api_key: "optional_api_key"
    adapters:                           # 适配器配置
      outbound:                         # 出站配置（向上游发送）
        click:                          # 点击事件配置
          method: "GET"                 # HTTP方法
          url: "https://api.upstream-a.com/click?aid={{aid}}&cid={{cid}}&sig={{sig}}"
          macros:                       # URL宏定义
            aid: "udm.ad.ad_id | url_encode()"
            cid: "udm.ad.campaign_id | url_encode()"
            sig: "hmac_sha256(secret_ref('secret'), join('&',[aid,cid]))"
          timeout_ms: 1000              # 超时时间（毫秒）
          retry: {max: 2, backoff_ms: 200}  # 重试配置
      inbound_callback:                 # 回调入站配置（接收上游回调）
        event:
          source: "query"               # 参数来源：query/body
          field_map:                    # 字段映射
            "udm.click.id": "query.click_id"
            "udm.event.name": "query.event_type"
          verify:                       # 签名验证
            type: "hmac_sha256"
            signature: "query.sig"
            message: "join('&',[query.click_id,query.event_type])"
            secret_ref: "secret"
```

### 下游配置 (downstreams)

```yaml
downstreams:
  - id: "downstream_b"                  # 下游唯一标识
    name: "下游B"                       # 下游名称（可选）
    secrets:                            # 下游相关密钥
      secret: "downstream_b_secret"
    adapters:                           # 适配器配置
      outbound_callback:                # 回调出站配置（向下游发送回调）
        event:
          method: "GET"                 # 使用GET方法
          url: "https://api.downstream-b.com/callback?click_id={{click_id}}&event={{event}}&sign={{sign}}"
          macros:                       # URL宏定义
            click_id: "udm.click.id | url_encode()"
            event: "udm.event.name | url_encode()"
            sign: "hmac_sha256(secret_ref('secret'), join('|',[click_id,event]))"
          retry: {max: 3, backoff_ms: 500}
```

### 路由配置 (routes)

```yaml
routes:
  - match_key: "campaign_id"            # 匹配字段
    rules:                              # 匹配规则
      - equals: "cmp_123"               # 精确匹配
        upstream: "upstream_a"          # 目标上游
        downstream: "downstream_b"      # 目标下游
      - equals: "cmp_456"
        upstream: "upstream_a"
        downstream: "downstream_b"
    fallback_upstream: "upstream_a"     # 兜底上游
    fallback_downstream: "downstream_b" # 兜底下游
```

## DSL表达式语法

系统支持强大的DSL表达式用于字段映射和数据转换：

### 基础语法

- `const:value` - 常量值
- `udm.field.path` - 访问UDM字段
- `query.param` - 访问URL参数
- `body.field` - 访问请求体字段
- `meta.ip` - 访问元数据（IP、UA等）

### 函数支持

- `to_upper()` - 转大写
- `to_lower()` - 转小写
- `url_encode()` - URL编码
- `trim()` - 去除空白
- `hash_md5()` - MD5哈希
- `hash_sha256()` - SHA256哈希

### 高级功能

- `secret_ref('key')` - 引用密钥
- `hmac_sha256(secret, message)` - HMAC签名
- `join(sep, [a,b,c])` - 字符串连接
- `cb_url()` - 生成回调URL
- `field | func1() | func2()` - 管道操作

### 示例

```yaml
macros:
  # 基础字段映射
  campaign_id: "udm.ad.campaign_id"
  
  # 函数处理
  device_id: "udm.device.idfa | to_upper()"
  
  # 签名生成
  signature: "hmac_sha256(secret_ref('secret'), join('&',[campaign_id,device_id]))"
  
  # 回调URL
  callback_url: "cb_url()"
```

## 自测流程

### 1. 基础功能测试

```bash
# 测试点击上报（GET）
curl "http://localhost:8000/v1/track?event_type=click&ds_id=ds_demo&campaign_id=cmp_456&click_id=test_click_123&ts=1734508800000"
```

### 2. 查看上游请求

检查日志输出，确认系统正确调用了上游接口（httpbin.org）。

### 3. 模拟上游回调

从上游请求的响应中获取回调URL，然后模拟上游回调：

```bash
# 从httpbin响应中找到cb参数的值，提取token
# 然后调用回调接口
curl "http://localhost:8000/cb/{token}?clid=test_click_123&event_name=install&ts=1734508800&sig=calculated_signature"
```

### 4. 验证下游回调

检查日志，确认系统正确回调了下游接口。

## 数据管理

### 数据库配置

系统使用MySQL数据库，需要通过环境变量配置连接信息：

```bash
export MYSQL_HOST=your_mysql_host
export MYSQL_USER=your_mysql_user  
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DB=your_mysql_database
```

- 表结构：
  - `request_log` - 统一日志记录表

### 数据查询

```bash
# 连接数据库
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB

# 查看事件统计
SELECT ds_id, event_type, COUNT(*) FROM request_log GROUP BY ds_id, event_type;

# 查看请求详情  
SELECT rid, ds_id, up_id, event_type, created_at FROM request_log ORDER BY created_at DESC LIMIT 10;
```

## 生产部署建议

### 1. 环境配置

```bash
# 使用生产级WSGI服务器
pip install gunicorn

# 启动命令
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 2. 反向代理

使用Nginx作为反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. 监控告警

- 监控接口响应时间和成功率
- 监控数据库连接状态
- 监控上游/下游接口状态
- 设置异常告警

### 4. 数据备份

```bash
# MySQL数据库备份
mysqldump -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB > backup_$(date +%Y%m%d).sql

# 定期备份脚本示例
0 2 * * * mysqldump -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB | gzip > /backup/ocpx-$(date +\%Y\%m\%d).sql.gz
```

## 常见问题

### Q: 如何添加新的上游？

A: 在 `config.yaml` 的 `upstreams` 部分添加新配置，然后重启服务。

### Q: 如何修改路由规则？

A: 修改 `config.yaml` 的 `routes` 部分，支持热重载（重启服务生效）。

### Q: 如何查看详细日志？

A: 检查应用日志输出，每个请求都有唯一的 `trace_id` 用于追踪。

### Q: 如何优化数据库性能？

A: 建议定期监控MySQL数据库性能，为高频查询字段添加索引，定期清理历史数据。

## 技术支持

如需技术支持，请提供：
- 配置文件内容
- 错误日志
- 请求示例
- trace_id

---

**版本**: v1.0.0  
**更新时间**: 2024-12-18
