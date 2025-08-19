# OCPX 中转系统 - 配置与联调教程（v2）

本教程与当前实现保持一致，覆盖快速启动、路由配置、上游适配、回调闭环联调等。

---

## 一、快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动（开发）
python start.py --host 0.0.0.0 --port 6789 --reload

# 访问
curl 'http://127.0.0.1:6789/health'
```

> 当前优先加载 `config_notnull.yaml`，若需使用 `config.yaml`，可重命名/删除 `config_notnull.yaml` 或在后续扩展 --config 参数。

---

## 二、关键配置说明

### 2.0 同一家上游、不同广告计划的“自定义常量”管理（纯配置）
当同一家上游的多个广告计划需要不同的固定自定义字段（如 x/a/sid 等），无需改代码，也无需让下游新增字段。方法是：
- 定义一份“公共 click 模板”（URL 与公共 macros）
- 为每个广告计划派生一个“上游实例”（id 不同），仅覆盖该计划的常量值
- 在 routes 中按 ad_id 精确匹配到对应的上游实例

示例：
```yaml
upstreams:
  - id: "adapi-base"
    adapters:
      outbound:
        click: &adapi_click_tpl
          method: "GET"
          url: "http://ad.adapi.cn/click?aid={{aid}}&did={{did}}&os={{os}}&ts={{ts}}&callback={{callback}}&x={{x}}&a={{a}}&sid={{sid}}"
          macros:
            aid: "udm.ad.ad_id | url_encode()"
            did: "const:kpk"
            os: "udm.device.os | to_upper()"
            ts: "udm.time.ts"
            callback: "cb_url() | url_encode()"
            # 待覆盖的“自定义常量”
            x:   "const:DEFAULT_X"
            a:   "const:DEFAULT_A"
            sid: "const:DEFAULT_SID"

  - id: "adapi-AD_68468c9a"
    adapters:
      outbound:
        click:
          <<: *adapi_click_tpl
          macros:
            <<: *adapi_click_tpl.macros
            x:   "const:X_FOR_68468c9a"
            a:   "const:A_FOR_68468c9a"
            sid: "const:SID_FOR_68468c9a"

  - id: "adapi-AD_10_60_683572_8"
    adapters:
      outbound:
        click:
          <<: *adapi_click_tpl
          macros:
            <<: *adapi_click_tpl.macros
            x:   "const:X_FOR_10_60_683572_8"
            a:   "const:A_FOR_10_60_683572_8"
            sid: "const:SID_FOR_10_60_683572_8"

routes:
  - match_key: "ad_id"
    rules:
      - equals: "68468c9ade037"
        upstream: "adapi-AD_68468c9a"
      - equals: "10_60_683572_8"
        upstream: "adapi-AD_10_60_683572_8"
    fallback_upstream: "adapi-base"
```
说明：公共模板统一维护，派生实例只覆盖常量；下游报文不变，按 ad_id 自动命中对应上游；无需任何代码变更。



### 2.1 上游适配（adapters.outbound）
- 使用 `click` 作为锚点模板 `&click_tpl`；`imp` 复用该模板（*click_tpl）
- URL 与 macros 通过 DSL 渲染：
  - 支持 `udm.*`、`url_encode()`、`to_upper()`、`cb_url()` 等

示例（NotNull）：
```yaml
upstreams:
  - id: "adapi"
    adapters:
      outbound:
        click: &click_tpl
          method: "GET"
          url: "http://ad.adapi.cn/click?aid={{aid}}&did={{did}}&os={{os}}&ts={{ts}}&callback={{callback}}&oaid={{oaid}}&imei={{imei}}&android_id={{android_id}}&idfa={{idfa}}&caid={{caid}}&ip={{ip}}&ua={{ua}}&model={{model}}&x={{x}}&clid={{clid}}"
          macros:
            aid: "udm.ad.ad_id | url_encode()"
            did: "const:kpk"
            os: "udm.device.os | to_upper()"
            ts: "udm.time.ts"
            callback: "cb_url() | url_encode()"
            oaid: "udm.device.oaid | url_encode()"
            imei: "udm.device.imei | url_encode()"
            android_id: "udm.device.android_id | url_encode()"
            idfa: "udm.device.idfa | url_encode()"
            caid: "udm.device.caid | url_encode()"
            ip: "udm.net.ip | url_encode()"
            ua: "udm.net.ua | url_encode()"
            model: "udm.device.model | url_encode()"
            x: "udm.meta.ext.custom_id | url_encode()"
            clid: "udm.click.id | url_encode()"
        imp: *click_tpl
```

### 2.2 路由配置（routes）
- 按 `ad_id` 匹配上游
```yaml
routes:
  - match_key: "ad_id"
    rules:
      - equals: "10_60_683572_8"
        upstream: "adapi"
    fallback_upstream: "adapi"
```

---

## 三、下游上报规范（GET /v1/track）
- 仅支持事件：`click` / `imp`
- 必填：`ds_id`、`event_type`、`ad_id`
- 强烈建议：`click_id`（幂等与回拨关联）、`callback`（动态模板闭环）
- 统一响应：`success`、`code`、`message`；`200=成功`，其余按HTTP状态码

示例：
```
---

## 七、数据表说明与查询示例（v2）

系统统一使用一张表 `request_log` 存储链路关键信息（track 与 callback），字段如下：
- rid：回调关联ID（等于 trace_id），唯一，用于 /cb?rid=... 定位记录
- ds_id：下游标识
- up_id：上游标识（路由命中后写入；有些场景可能为空）
- event_type：click/imp
- ad_id、click_id：广告ID/点击ID
- ts：事件时间（毫秒）
- os：设备系统（IOS/ANDROID，可空）
- upload_params：JSON，上报收到的原始参数
- callback_params：JSON，回调收到的原始参数
- upstream_url：上报上游最终URL
- downstream_url：最终回拨下游URL
- is_callback_sent：是否已成功回拨下游（0/1）
- callback_time：回拨成功时间（毫秒）
- callback_event_type：回调事件名（如 ACTIVATED/PAID/RETAINED）

### 常用查询示例（SQLite）
- 最近100条点击：
```sql
SELECT rid, ds_id, ad_id, click_id, ts FROM request_log
WHERE event_type='click'
ORDER BY id DESC LIMIT 100;
```
- 查看某条 rid 的完整链路：
```sql
SELECT * FROM request_log WHERE rid='RID_VALUE';
```
- 最近回拨成功的记录：
```sql
SELECT rid, downstream_url, callback_event_type, callback_time FROM request_log
WHERE is_callback_sent=1
ORDER BY callback_time DESC LIMIT 100;
```
- 按广告聚合统计当天点击量：
```sql
SELECT ad_id, COUNT(1) AS cnt
FROM request_log
WHERE event_type='click' AND ts BETWEEN :start_ms AND :end_ms
GROUP BY ad_id
ORDER BY cnt DESC;
```
- 查询上游最终URL包含特定上游域名的记录：
```sql
SELECT rid, upstream_url FROM request_log
WHERE upstream_url LIKE '%ad.adapi.cn%'
ORDER BY id DESC LIMIT 200;
```

http://127.0.0.1:6789/v1/track?event_type=click&ds_id=oneway&ad_id=10_60_683572_8&click_id=ck_001&ip=1.2.3.4&ua=Mozilla/5.0&device_os=IOS&device_model=iPhone13,2&os_version=15.1&device_idfa=IDFA-TEST&device_mac=00:11:22:33:44:55&ts=1734508800000&callback=https%3A%2F%2Fmedia.com%2Fcb%3Ftrack%3Dck_001%26event_type%3D__EVENT__
```

---

## 四、回调闭环联调

### 4.1 回调构造
- 我方生成给上游的回调：`https://cb.your-domain.com/cb?rid={trace_id}&<下游模板原有query>`
- 不再使用 token，不注入我方宏串

### 4.2 上游→我方回调
- 示例：
```
http://127.0.0.1:6789/cb?rid=RID&cbsid=7367...&cb_ow_type=1&event_type=ACTIVATED
```

### 4.3 我方→下游回拨
- 将“原始模板”中的宏替换为回调解析值，直接 GET 回拨
- 默认映射（可在 inbound_callback 中配置）：
  - 事件名：`udm.event.name` ← `query.event_type`
  - 金额：`udm.meta.amount` ← `query.amount`
  - 留存：`udm.meta.days` ← `query.days`

---

## 五、调试技巧
- 查看“准备向上游转发的 URL”日志：`[to-upstream] click url: ...`
- 回调链路日志：打印最终下游URL（可在代码中打开对应日志）
- 若返回 200 但不转发：检查是否命中 routes 或 fallback，确认实际加载的配置文件

---

## 六、FAQ
- Q：同一个 config 里可以配置多个上游并按 ad_id 路由吗？
  - A：可以；未命中走 fallback_upstream。
- Q：上游回调字段不是 event_type 怎么办？
  - A：在 inbound_callback.field_map 中改成对应字段名，如 `"udm.event.name": "query.evt"`。
- Q：下游上报字段想用别名（比如 reporting_type）？
  - A：默认不支持；建议使用规范字段或与我方沟通开启“别名归一化”配置。

---

版本：v2.0.0
更新时间：2025-08-19

