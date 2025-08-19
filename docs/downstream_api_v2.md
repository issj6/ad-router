# OCPX 中转系统 - 下游对接文档（v2）

本版本文档与系统当前实现保持一致：
- 接口统一为 GET
- 上报事件仅有 click/imp（注册/激活/付费/留存等为回调事件，不走 track）
- 广告维度仅保留 ad_id
- 时间戳统一毫秒（13位）
- 回调采用“动态模板闭环”：下游在点击上报时提供 callback 模板，我们回调时进行宏替换
- 统一响应：success、code、message；200 表示成功，其余与 HTTP 状态码一致

---

## 一、基础信息
- 域名示例：`https://your-domain.com`
- 协议：HTTPS
- 编码：UTF-8

## 二、统一上报接口（GET）
- 路径：`/v1/track`
- 用法：通过查询参数传入字段
- 事件类型：`event_type=click` 或 `event_type=imp`

示例：
```
GET /v1/track?event_type=click&ds_id=oneway&ad_id=ad_123&click_id=ck_001&ts=1734508800000&ip=1.2.3.4&ua=Mozilla/5.0&device_os=IOS&device_model=iPhone13,2&device_idfa=ABCD-...&os_version=15.1&device_mac=00:11:22:33:44:55&callback=https%3A%2F%2Fmedia.com%2Fcb%3Ftrack%3Dck_001%26event_type%3D__EVENT__
```

### 2.1 必填参数
| 名称 | 说明 | 示例 |
|---|---|---|
| ds_id | 下游标识 | oneway |
| event_type | 事件类型：click 或 imp | click |
| ad_id | 广告ID | ad_123 |

### 2.2 强烈建议
| 名称 | 说明 | 示例 |
|---|---|---|
| click_id | 点击ID（用于幂等与回传关联） | ck_001 |
| callback | 回调模板URL（需URL编码；见“回调闭环”） | https%3A%2F%2Fmedia.com%2Fcb%3Ftrack%3Dck_001%26event_type%3D__EVENT__ |

### 2.3 其他参数
| 名称 | 说明 | 示例 |
|---|---|---|
| ts | 时间戳（毫秒，13位；不传则服务器填充） | 1734508800000 |
| ip | 设备公网IP（不传则取请求源IP） | 1.2.3.4 |
| ua | User-Agent（不传则取请求头 UA） | Mozilla/5.0 |
| device_os | 设备OS | IOS/ANDROID |
| device_model | 设备型号 | iPhone13,2 |
| device_idfa | iOS 广告标识 | ABCD-... |
| device_caid | iOS CAID | caid_xxx |
| device_oaid | Android OAID | oaid_xxx |
| device_imei | Android IMEI | 86... |
| device_android_id | Android ID | a1b2c3... |
| os_version | 系统版本 | 15.1 |
| device_mac | 设备 MAC | 00:11:22:33:44:55 |
| user_phone_md5 | 手机号MD5（脱敏） | md5_xxx |
| user_email_sha256 | 邮箱SHA256（脱敏） | sha256_xxx |
| ext_custom_id | 扩展自定义标识 | xyz_001 |

注意：所有参数均为 query 形式，无需传 JSON 体。

## 三、响应格式
- 统一返回：
```
{
  "success": true,
  "code": 200,
  "message": "ok"
}
```
- 规则：`code=200` 表示成功；失败与 HTTP 状态码一致（例如 400/401/403/404/408/5xx）

## 四、幂等性说明
- 当日内以 `(ds_id, event_type, click_id)` 去重；重复上报不会重复记账
- 重复上报返回也为 `code=200`（幂等成功），系统内部会忽略重复写入

## 五、回调接收（动态模板闭环）
- 下游在点击上报时提供 `callback` 模板（需 URL 编码）。模板中可包含大小写不敏感的宏：
  - `__EVENT__/__EVENT_TYPE__/__EVENTTYPE__/__EVT__/__TYPE__` → 替换为上游回调的事件名（例如 ACTIVATED）
  - `__CLICK_ID__/__CLICKID__/__CLID__/__CLKID__` → 替换为点击ID
  - `__AMOUNT__/__PRICE__/__VALUE__` → 替换为金额（付费事件）
  - `__DAYS__/__RETENTION__/__RETAIN_DAYS__` → 替换为留存天数（留存事件）
- 我方会把下游提供的模板“保留原查询参数”，仅替换 base 为我方回调入口并追加 `rid`：
  - 上游使用的回调：`https://cb.your-domain.com/cb?rid={trace_id}&<下游模板原有query>`
- 上游回调到我方后：
  1. 我方按 `rid` 找回原始模板
  2. 根据上游回调 query（例如 `event_type=ACTIVATED`）映射为 UDM
  3. 进行宏替换，得到最终下游回调 URL
  4. 以 GET 请求回拨给下游

示例（下游原始模板，未编码）：
```
https://media.com/cb?track=ck_001&event_type=__EVENT__
```
上报时需 URL 编码后放入 `callback` 参数。

## 六、字段命名规范与建议
- 使用本文档的标准字段名；如需兼容既有字段（如 `reporting_type`、`callback_url` 等），可在网关层做改写或与我方沟通添加别名映射（配置化）
- 设备字段统一以 `device_` 前缀（除 os_version、ua、ip）

## 七、常见问题（FAQ）
- Q：必须传 `click_id` 吗？
  - A：强烈建议。没有 `click_id` 会削弱幂等与回拨关联能力。
- Q：`ts` 可以传 10 位秒级吗？
  - A：建议传 13 位毫秒。不传则服务器自动填充毫秒时间。
- Q：回调的事件不是 `event_type`，而是 `evt`？
  - A：上游→我方的回调字段名可配置，我们会在服务端做解析映射，不影响你们的模板宏。

---

版本：v2.0.0
更新时间：2025-08-19

