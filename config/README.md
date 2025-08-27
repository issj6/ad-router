# 多文件配置说明

这个目录包含了拆分后的多文件配置结构，相比单文件配置具有更好的可维护性和可扩展性。

## 目录结构

```
config/
├── main.yaml           # 主配置文件（系统设置 + 路由规则）
├── upstreams/          # 上游配置目录
│   ├── adapi.yaml      # 微风互动上游配置
│   └── duokaiyou.yaml  # 多开游上游配置
├── downstreams/        # 下游配置目录（可选）
└── README.md          # 本说明文件
```

## 使用方法

### 方法1: 环境变量
```bash
export CONFIG_DIR=/Users/yang/PycharmProjects/adRouter/config
python app/main.py
```

### 方法2: 命令行参数
```bash
CONFIG_DIR=./config python app/main.py
```

### 方法3: 远程主配置
```bash
export MAIN_CONFIG_URL=https://your-domain.com/config/main.yaml
python app/main.py
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

### 合并为单文件（如需要）
```bash
python tools/config_manager.py merge ./config merged_config.yaml
```

## 配置文件说明

### main.yaml
包含系统基础设置、上游配置文件引用列表和路由规则。

### upstreams/*.yaml
每个文件对应一个上游广告平台的完整配置，包括：
- 基本信息（ID、名称、描述）
- 密钥配置
- 出站适配器（向上游发送请求）
- 入站回调适配器（处理上游回调）

### downstreams/*.yaml
每个文件对应一个下游媒体方的配置（可选），包括：
- 基本信息
- 回调配置
- 签名验证等

## 优势

1. **模块化管理**: 每个上游独立配置文件，便于维护
2. **团队协作**: 不同人员可以维护不同的上游配置
3. **版本控制**: 可以单独跟踪每个上游的配置变更
4. **灵活部署**: 支持本地和远程混合配置
5. **向下兼容**: 系统会自动兼容原有的单文件配置

## 注意事项

1. 上游配置文件中的 `id` 字段必须与 `main.yaml` 中声明的 `id` 一致
2. 路由规则中引用的上游ID必须在已加载的上游配置中存在
3. 配置文件使用UTF-8编码
4. YAML语法严格，注意缩进和引号使用

## 故障排除

如果遇到配置加载问题：

1. 使用 `python tools/config_manager.py validate ./config` 验证配置
2. 检查日志输出中的详细错误信息
3. 确认文件路径和权限正确
4. 验证YAML语法正确性

## 迁移指南

从单文件配置迁移到多文件配置：

```bash
# 1. 拆分现有配置
python tools/config_manager.py split config.yaml ./config

# 2. 验证拆分结果
python tools/config_manager.py validate ./config

# 3. 设置环境变量
export CONFIG_DIR=./config

# 4. 启动服务
python app/main.py
```
