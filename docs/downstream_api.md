# OCPX中转系统 - 下游对接文档

## 概述

OCPX中转系统为下游媒体方提供统一的广告追踪接口，无论上游广告主的接口如何变化，下游只需对接我们的统一接口即可。

## 接口特点

- **无需鉴权**：所有接口均为公开接口，无需token或签名
- **统一格式**：所有下游使用相同的接口格式和字段定义
- **高可用**：支持高并发，自动重试，幂等保护
- **实时响应**：同步返回处理结果

## 基础信息

- **接口域名**：`https://your-domain.com`（请替换为实际域名）
- **协议**：HTTPS
- **格式**：JSON
- **编码**：UTF-8

## 统一上报接口

### 1. 点击/曝光上报（合并模板，同一接口）

**接口地址**：`GET /v1/track?event_type=click&...`

**请求示例**：
```bash
curl "https://your-domain.com/v1/track?event_type=click&ds_id=your_downstream_id&campaign_id=cmp_456&click_id=ck_abc123&ts=1734508800000&ip=1.2.3.4&ua=Mozilla/5.0&device_os=iOS&device_idfa=ABCD-1234-EFGH-5678"
```

（按事件类型以 event_type=imp/click 区分，无需单独接口）

**接口地址**：`GET /v1/track?event_type=imp&...`

**请求示例**：
```bash
curl "https://your-domain.com/v1/track?event_type=imp&ds_id=your_downstream_id&campaign_id=cmp_456&ts=1734508800000&device_os=iOS&device_idfa=ABCD-1234-EFGH-5678"
```

### 3. 转化事件上报

**接口地址**：`GET /v1/track?event_type=event&...`

**请求示例**：
```bash
curl "https://your-domain.com/v1/track?event_type=event&event_name=install&ds_id=your_downstream_id&campaign_id=cmp_456&click_id=ck_abc123&ts=1734508800000"
```

## 请求参数说明

### 必填参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| ds_id | string | 下游标识ID，用于识别请求来源 | "your_downstream_id" |
| event_type | string | 事件类型：click/imp/event | "click" |

### 可选参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| event_name | string | 事件名称，event类型时使用 | "install", "register", "pay" |
| ad_id | string | 广告ID | "ad_123" |
| campaign_id | string | 计划ID | "cmp_456" |
| adgroup_id | string | 广告组ID | "adg_789" |
| creative_id | string | 创意ID | "cre_101" |
| click_id | string | 点击ID，click和event类型推荐必传 | "ck_abc123" |
| ts | integer | 时间戳（毫秒，13位），不传则使用服务器时间 | 1734508800000 |
| ip | string | 用户IP地址 | "1.2.3.4" |
| ua | string | User-Agent | "Mozilla/5.0..." |
| device | object | 设备信息 | 见下表 |
| user | object | 用户信息（仅接受哈希值） | 见下表 |
| ext | object | 扩展字段，任意键值对 | {"slot": "banner"} |

### 设备信息字段 (device)

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| idfa | string | iOS广告标识符 | "ABCD-1234-EFGH-5678" |
| gaid | string | Google广告ID | "12345678-1234-1234-1234-123456789abc" |
| oaid | string | 开放匿名设备标识符 | "oaid_example" |
| android_id_md5 | string | Android ID的MD5值 | "md5_hash_value" |
| imei_md5 | string | IMEI的MD5值 | "md5_hash_value" |
| os | string | 操作系统 | "iOS", "Android" |
| os_version | string | 系统版本 | "14.0", "11" |
| model | string | 设备型号 | "iPhone12,1", "SM-G973F" |

### 用户信息字段 (user)

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| phone_md5 | string | 手机号MD5值 | "md5_hash_value" |
| email_sha256 | string | 邮箱SHA256值 | "sha256_hash_value" |

## 响应格式

### 成功响应

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "trace_id": "12345678-1234-1234-1234-123456789abc",
    "click_id": "ck_abc123",
    "upstream_status": 200
  }
}
```

### 错误响应

```json
{
  "code": 1002,
  "msg": "invalid_param",
  "data": {
    "trace_id": "12345678-1234-1234-1234-123456789abc"
  }
}
```

## 错误码说明

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 0 | 成功 | - |
| 1002 | 参数错误 | 检查请求参数格式和必填字段 |
| 2001 | 上游超时 | 可以重试 |
| 2002 | 上游错误 | 可以重试 |
| 5000 | 服务器错误 | 可以重试 |

## 幂等性说明

系统基于 `(ds_id, event_type, click_id)` 在当日内实现幂等性：

- 相同的组合在同一天内多次上报，只会记录第一次
- 重复请求返回 `code=0`，但 `msg` 可能包含 "duplicate" 提示
- 建议在网络异常时进行重试，系统会自动去重

## 回调接收（动态模板闭环）

当发生转化事件（如激活、注册、付费等）时，系统会回调“下游在点击上报时提供的 callback 模板”。
- 下游需要将 callback 模板进行 URL 编码后放入 callback 参数
- 模板中可包含宏（大小写不敏感）：__EVENT__/__EVENT_TYPE__/__CLICK_ID__/__AMOUNT__/__DAYS__ 等
- 我方会在收到上游回调后，按 inbound 映射解析出 UDM 值，将模板中的宏替换为实际值，然后以 GET 方式回拨
- 不再需要在配置文件维护下游回调URL或签名（无兜底配置），一切以下游模板为准

## 测试建议

1. **功能测试**：使用不同的 `ds_id` 和 `campaign_id` 测试路由是否正确
2. **幂等测试**：重复发送相同的请求，验证去重功能
3. **异常测试**：测试网络超时、参数错误等异常情况
4. **性能测试**：测试高并发场景下的接口性能

## 技术支持

如有技术问题，请联系技术支持团队，并提供：
- 请求的完整参数
- 响应结果
- trace_id（用于日志追踪）
- 发生时间

## 更新日志

- v1.0.0 (2024-12-18): 初始版本发布
