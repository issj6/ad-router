import os
import sys
import json
import yaml
import logging
import httpx
from typing import Any, Dict

# 配置日志格式，确保配置下载日志能显示
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def download_online_config() -> Dict[str, Any]:
    """下载在线配置文件"""
    online_config_url = "https://gitee.com/yang0000111/files/raw/master/ad-router-config.yaml"
    
    logging.info(f"正在下载在线配置文件: {online_config_url}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(online_config_url)
            response.raise_for_status()  # 检查HTTP状态码
            
            if not response.text.strip():
                raise ValueError("在线配置文件内容为空")
            
            # 解析YAML
            config_data = yaml.safe_load(response.text)
            
            if not isinstance(config_data, dict):
                raise ValueError("在线配置文件格式错误：根节点必须是字典类型")
            
            # 基础字段验证
            required_fields = ["settings", "upstreams", "routes"]
            missing_fields = [field for field in required_fields if field not in config_data]
            if missing_fields:
                raise ValueError(f"在线配置文件缺少必要字段: {', '.join(missing_fields)}")
            
            # 确保有downstreams字段（可以为空列表）
            if "downstreams" not in config_data:
                config_data["downstreams"] = []
            
            logging.info("在线配置文件下载并验证成功")
            return config_data
            
    except httpx.RequestError as e:
        logging.error(f"❌ 网络请求错误: {e}")
        logging.error("📋 解决方案:")
        logging.error("   1. 检查网络连接是否正常")
        logging.error(f"   2. 确认URL是否可访问: {online_config_url}")
        logging.error("   3. 检查防火墙设置")
        sys.exit(1)
        
    except httpx.HTTPStatusError as e:
        logging.error(f"❌ HTTP错误 {e.response.status_code}: {e}")
        if e.response.status_code == 404:
            logging.error("📋 解决方案: 确认在线配置文件是否存在")
        elif e.response.status_code == 403:
            logging.error("📋 解决方案: 检查在线配置文件的访问权限")
        else:
            logging.error("📋 解决方案: 检查在线配置文件服务状态")
        sys.exit(1)
        
    except yaml.YAMLError as e:
        logging.error(f"❌ 在线配置文件YAML语法错误: {e}")
        logging.error("📋 解决方案:")
        logging.error("   1. 检查在线配置文件的YAML格式")
        logging.error("   2. 使用YAML验证工具检查语法")
        logging.error("   3. 参考本地 config.yaml 的正确格式")
        sys.exit(1)
        
    except ValueError as e:
        logging.error(f"❌ 配置验证失败: {e}")
        logging.error("📋 解决方案:")
        logging.error("   1. 确保在线配置包含所有必要字段")
        logging.error("   2. 参考本地 config.yaml 的完整结构")
        sys.exit(1)
        
    except Exception as e:
        logging.error(f"❌ 加载在线配置时发生未知错误: {e}")
        logging.error("📋 解决方案: 请联系技术支持")
        sys.exit(1)


def load_config() -> Dict[str, Any]:
    """严格的在线配置加载，失败时终止启动"""
    return download_online_config()

# 全局配置对象
CONFIG = load_config()
