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

