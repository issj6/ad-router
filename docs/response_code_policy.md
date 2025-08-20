# 返回码策略文档

## 统一返回码规范

为了简化客户端的错误处理逻辑，本系统采用了统一的返回码策略：

### 业务接口返回码

#### 1. Track接口 (`/v1/track`)
- **成功 (200)**: 请求成功处理并成功转发到上游
- **失败 (500)**: 任何失败情况，包括但不限于：
  - 参数验证失败（如无效的event_type）
  - 找不到匹配的上游路由
  - 上游配置缺失
  - 上游请求失败
  - 系统内部错误

#### 2. Callback接口 (`/cb`)
- **成功 (200)**: 回调成功处理并成功转发到下游
- **失败 (500)**: 任何失败情况，包括但不限于：
  - 缺少必需参数（如rid）
  - 签名验证失败
  - 下游回调失败
  - 系统内部错误

### 系统接口返回码

#### 1. 健康检查接口 (`/` 和 `/health`)
- 始终返回 **200**，通过响应体中的字段表示状态：
  ```json
  {
    "ok": true,      // 服务是否正常
    "timestamp": 1234567890,
    "version": "1.0.0",
    "db_ok": true    // 数据库连接状态（仅/health接口）
  }
  ```

## 实施说明

### 为什么采用这种策略？

1. **简化客户端逻辑**：客户端只需要判断 200 和非 200，无需处理复杂的错误码映射
2. **隐藏内部细节**：不暴露系统内部的具体错误类型，增强安全性
3. **统一错误处理**：所有错误都按照相同的方式处理，减少特殊情况

### 错误详情

虽然HTTP状态码统一为500，但响应体中仍然包含有用的错误信息：

```json
{
  "success": false,
  "code": 500,
  "message": "链接已关闭"  // 具体的错误描述
}
```

### 日志记录

所有详细的错误信息都会记录在服务器日志中，包括：
- 原始错误类型
- 详细的错误堆栈
- 请求的trace_id用于问题追踪

## 客户端集成示例

```python
# Python示例
response = requests.get("http://api.example.com/v1/track", params={...})

if response.status_code == 200:
    # 处理成功
    data = response.json()
    print("Success:", data["message"])
else:
    # 处理失败（统一为500）
    error = response.json()
    print("Error:", error["message"])
    # 记录错误日志或重试
```

```javascript
// JavaScript示例
fetch('http://api.example.com/v1/track?' + params)
  .then(response => {
    if (response.status === 200) {
      // 成功处理
      return response.json();
    } else {
      // 失败处理（统一为500）
      throw new Error('Request failed');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    // 错误处理或重试逻辑
  });
```

## 版本历史

- **v1.1.0** (2024-12): 统一返回码策略，所有业务错误返回500
- **v1.0.0** (初始版本): 使用多种HTTP状态码（400, 404, 500等）
