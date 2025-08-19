import os
import json
import yaml
from typing import Any, Dict

def load_config() -> Dict[str, Any]:
    """加载配置文件，优先级：config.yaml > config.json > 默认配置"""
    # 优先 yaml, 再 json, 再 py（config.py内置）
    if os.path.exists("config_notnull.yaml"):
        with open("config_notnull.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 默认兜底配置（最小可用）
    return {
        "settings": {
            "callback_base": "https://cbkpk.notnull.cc",
            "timezone": "Asia/Shanghai",
            "data_dir": "./data/sqlite",
            "app_secret": "CHANGE_ME_TO_RANDOM_SECRET"
        },
        "upstreams": [],
        "downstreams": [],
        "routes": []
    }

# 全局配置对象
CONFIG = load_config()
