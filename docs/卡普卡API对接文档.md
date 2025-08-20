- ### 基础信息

    - **接口协议：** HTTP
    - **请求方式：** GET
    - **编码格式：** UTF-8
    - **响应格式：** JSON

    1. ## 事件上报接口

    ### 接口地址

    GET http://tkapi.notnull.cc:6789/v1/track

    ### 参数（没有的参数留空）

    | 参数名            | 类型   | 说明                                                         | 是否必填 | 示例                                                         |
    | ----------------- | ------ | ------------------------------------------------------------ | -------- | ------------------------------------------------------------ |
    | ds_id             | string | 我方提供，用于媒体标识                                       | 是       | xxx                                                          |
    | event_type        | string | 事件类型：click（点击）/ imp（曝光） 通常事件上报类型如无特殊说明，只需上报点击事件 | 是       | click                                                        |
    | ad_id             | string | 我方提供，用于标识广告                                       | 是       | ad_12345                                                     |
    | click_id          | string | 点击唯一标识，建议使用随机UUID                               | 是       | ck_abc123                                                    |
    | callback          | string | 回调URL（需一次URL编码，见回调说明）                         | 是       | [https%3a%2f%2fxxx.com](http://https%3a%2f%2fxxx.com)%2fcallback%3fevent_type%3d__EVENT__ |
    | ts                | int    | 事件时间戳（13位毫秒）                                       | 是       | 1700000000000                                                |
    | ip                | string | 用户IP（IPV4或IPV6）                                         | 否       | 192.168.1.100                                                |
    | ua                | string | User-Agent（需一次URL编码）                                  | 否       | Mozilla/5.0...                                               |
    | device_os         | string | 操作系统（ANDROID、IOS二选一）                               | 是       | IOS / ANDROID                                                |
    | device_model      | string | 设备型号                                                     | 否       | iPhone13,2                                                   |
    | device_idfa       | string | iOS广告标识符 （IOS时与device_caid至少填其一）               | 是       | ABCD-1234-...                                                |
    | device_caid       | string | iOS CAID （IOS时与device_idfa至少填其一）                    | 是       | caid_xxx                                                     |
    | device_oaid       | string | Android OAID  （ANDROID时OAID、IMEI、ANDROID ID至少填其一）  | 是       | oaid_xxx                                                     |
    | device_imei       | string | Android IMEI  （ANDROID时OAID、IMEI、ANDROID ID至少填其一）  | 是       | 860123456789012                                              |
    | device_android_id | string | Android ID  （ANDROID时OAID、IMEI、ANDROID ID至少填其一）    | 是       | a1b2c3d4e5f6                                                 |
    | device_os_version | string | 系统版本                                                     | 否       | 15.8                                                         |
    | device_mac        | string | 设备MAC地址（需一次URL编码）                                 | 否       | 00:11:22:33:44:55                                            |
    | ext_custom_id     | string | 自定义扩展标识，若提供则必填                                 | 否       | custom_123                                                   |

    ### 请求示例

    ```Plain
    http://tkapi.notnull.cc:6789/v1/track?ds_id=xxx&event_type=click&ad_id=12345&click_id=b9c7e1b4-7f1a-4e8c-9d0b-8e6f5c4a3b2d&callback=http%3A%2F%2Fyourapp.com%2Fcallback%3Fcustom_param%3D123&ts=1700000000000&ip=198.51.100.1&ua=Mozilla%2F5.0%20(iPhone%3B%20CPU%20iPhone%20OS%2015_8%20like%20Mac%20OS%20X)%20AppleWebKit%2F605.1.15%20(KHTML%2C%20like%20Gecko)%20Version%2F15.0%20Mobile%2F15E148%20Safari%2F604.1&device_os=IOS&device_model=iPhone13,2&device_idfa=AEBE52E7-03EE-455A-B3C4-E57283966239&device_caid=caid_example_string_12345&device_oaid=&device_imei=&device_android_id=&device_os_version=15.8&device_mac=02:00:00:%2000:00:00&ext_custom_id=xxx
    ```

    ### 响应格式

    ```JSON
    {
      "success": true,
      "code": 200,
      "message": "ok"
    }
    ```

    **状态码说明：**

    - `200`：成功

    - `400`：参数错误

    - `408`：上游超时

    - `500`：服务器错误

        ## 回调处理机制

    ### 回调流程

    1. **媒体方上报时提供****回调****模板**
        1. 在 `callback` 参数中传入回调URL模板
        2. 模板中需要包含宏变量`__EVENT__`、`__AMOUNT__`、`__DAYS__`（没有可留空）
        3. 可加入其他用于标识的自定义字段，我方将原值传回
        4. 必须进行一次URL编码
    2. **回调****触发**
        1. 用户完成转化行为时，我方替换宏变量并调用回调地址

    ### 回调模板宏变量

    | 宏变量     | 说明                 | 示例值    |
    | ---------- | -------------------- | --------- |
    | __EVENT__  | 转化事件名称         | ACTIVATED |
    | __AMOUNT__ | 转化金额（付费事件） | 6.99      |
    | __DAYS__   | 留存天数（留存事件） | 7         |

    ### 转化事件类型

    | 事件类型   | 描述 |
    | ---------- | ---- |
    | ACTIVATED  | 激活 |
    | REGISTERED | 注册 |
    | PAID       | 付费 |
    | RETAINED   | 留存 |

    ### 回调模板示例

    **原始模板（需****URL****编码）：**

    https://xxx.com/callback?event_type=__EVENT__&amount=__AMOUNT__

    **URL****编码后：**

    https%3a%2f%2fxxx.com%2fcallback%3fevent_type%3d__EVENT__

    **最终回拨（宏替换后）：**

    https://xxx.com/callback?event_type=ACTIVATED&amount=6.99

    1. ## 错误处理

    | 错误码 | 说明             | 解决方案                        |
    | ------ | ---------------- | ------------------------------- |
    | 400    | 参数错误         | 检查必填参数是否完整            |
    | 400    | 不支持的事件类型 | 确保 event_type 为 click 或 imp |
    | 408    | 上游超时         | 稍后重试                        |
    | 500    | 服务器内部错误   | 联系技术支持                    |

    ### 重试策略

    - **建议重试**：408、5xx 错误
    - **不建议重试**：400 参数错误
    - **重试间隔**：建议指数退避，初始间隔 1 秒

    1. ## 其他

    - **文档版本**：v2.0.0
    - **更新时间**：2025-08-20
