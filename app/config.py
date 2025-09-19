import os
import yaml
import httpx
from typing import Any, Dict, List, Optional
from pathlib import Path
from .utils.logger import info, warning, error


class MultiConfigLoader:
    """多文件配置加载器"""
    
    def __init__(self, main_config_url: str = None, local_config_dir: str = None):
        self.main_config_url = main_config_url
        self.local_config_dir = Path(local_config_dir) if local_config_dir else Path("config")
        self.client = httpx.Client(timeout=30.0)
    
    def load_config(self) -> Dict[str, Any]:
        """加载完整配置"""
        try:
            # 1. 加载主配置文件
            main_config = self._load_main_config()
            
            # 2. 加载上游配置文件
            upstreams = self._load_upstream_configs(main_config.get("upstream_configs", []))
            
            # 3. 加载下游配置文件（如果有）
            downstreams = self._load_downstream_configs(main_config.get("downstream_configs", []))
            
            # 4. 合并配置
            final_config = {
                "settings": main_config.get("settings", {}),
                "upstreams": upstreams,
                "downstreams": downstreams,
                "routes": main_config.get("routes", [])
            }
            
            # 5. 验证配置
            self._validate_config(final_config)
            
            info(f"✅ 多文件配置加载成功: {len(upstreams)} 个上游, {len(downstreams)} 个下游")
            return final_config
            
        except Exception as e:
            error(f"❌ 多文件配置加载失败: {e}")
            raise
    
    def _load_main_config(self) -> Dict[str, Any]:
        """加载主配置文件"""
        if self.main_config_url:
            # 从远程加载
            info(f"📥 正在下载主配置文件: {self.main_config_url}")
            response = self.client.get(self.main_config_url)
            response.raise_for_status()
            config = yaml.safe_load(response.text)
        else:
            # 从本地加载
            main_file = self.local_config_dir / "main.yaml"
            if not main_file.exists():
                raise FileNotFoundError(f"主配置文件不存在: {main_file}")
            
            info(f"📁 正在加载本地主配置文件: {main_file}")
            with open(main_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        
        # 验证主配置结构
        required_fields = ["settings"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise ValueError(f"主配置文件缺少必要字段: {', '.join(missing_fields)}")
        
        return config
    
    def _load_upstream_configs(self, upstream_config_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """加载上游配置文件"""
        upstreams = []
        loaded_ids = set()  # 用于检查ID重复
        
        for config_def in upstream_config_list:
            try:
                # 获取声明的上游ID
                declared_id = config_def.get("id")
                if not declared_id:
                    warning(f"⚠️  上游配置缺少ID字段: {config_def}")
                    continue
                
                # 检查ID重复
                if declared_id in loaded_ids:
                    raise ValueError(f"上游ID重复: {declared_id}")
                loaded_ids.add(declared_id)
                
                # 检查是否启用
                if not config_def.get("enabled", True):
                    info(f"⏸️  跳过已禁用的上游: {declared_id}")
                    continue
                
                source = config_def.get("source", "local")
                config_name = config_def.get("name", declared_id)
                
                # 加载配置文件
                if source == "remote":
                    url = config_def["url"]
                    response = self.client.get(url)
                    response.raise_for_status()
                    upstream_config = yaml.safe_load(response.text)
                    info(f"📥 远程加载上游配置: {config_name} ({declared_id}) <- {url}")
                    
                elif source == "local":
                    path = config_def["path"]
                    full_path = self.local_config_dir / path
                    
                    if not full_path.exists():
                        if config_def.get("required", False):
                            raise FileNotFoundError(f"必需的上游配置文件不存在: {full_path}")
                        else:
                            warning(f"⚠️  可选的上游配置文件不存在: {full_path}")
                            continue
                    
                    with open(full_path, 'r', encoding='utf-8') as f:
                        upstream_config = yaml.safe_load(f)
                    info(f"📁 本地加载上游配置: {config_name} ({declared_id}) <- {path}")
                
                else:
                    warning(f"⚠️  未知的配置源类型: {source}")
                    continue
                
                # 验证配置文件中的ID与声明的ID是否一致
                file_id = upstream_config.get("id")
                if file_id != declared_id:
                    raise ValueError(
                        f"上游配置ID不匹配: 声明ID='{declared_id}', 文件ID='{file_id}', "
                        f"配置文件: {config_def.get('path', config_def.get('url'))}"
                    )
                
                # 验证上游配置结构
                self._validate_upstream_config(upstream_config)
                
                # 添加元数据
                upstream_config["_metadata"] = {
                    "source": source,
                    "name": config_name,
                    "loaded_from": config_def.get("path", config_def.get("url")),
                    "required": config_def.get("required", False)
                }
                
                upstreams.append(upstream_config)
                
            except Exception as e:
                error_msg = f"❌ 加载上游配置失败 {declared_id}: {e}"
                error(error_msg)
                
                # 如果是必需配置，抛出异常
                if config_def.get("required", False):
                    raise Exception(error_msg) from e
                
                continue
        
        return upstreams
    
    def _load_downstream_configs(self, downstream_config_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """加载下游配置文件"""
        downstreams = []
        loaded_ids = set()
        
        for config_def in downstream_config_list:
            try:
                declared_id = config_def.get("id")
                if not declared_id:
                    warning(f"⚠️  下游配置缺少ID字段: {config_def}")
                    continue
                
                if declared_id in loaded_ids:
                    raise ValueError(f"下游ID重复: {declared_id}")
                loaded_ids.add(declared_id)
                
                if not config_def.get("enabled", True):
                    info(f"⏸️  跳过已禁用的下游: {declared_id}")
                    continue
                
                source = config_def.get("source", "local")
                config_name = config_def.get("name", declared_id)
                
                if source == "remote":
                    url = config_def["url"]
                    response = self.client.get(url)
                    response.raise_for_status()
                    downstream_config = yaml.safe_load(response.text)
                    info(f"📥 远程加载下游配置: {config_name} ({declared_id}) <- {url}")
                    
                elif source == "local":
                    path = config_def["path"]
                    full_path = self.local_config_dir / path
                    
                    if not full_path.exists():
                        if config_def.get("required", False):
                            raise FileNotFoundError(f"必需的下游配置文件不存在: {full_path}")
                        else:
                            warning(f"⚠️  可选的下游配置文件不存在: {full_path}")
                            continue
                    
                    with open(full_path, 'r', encoding='utf-8') as f:
                        downstream_config = yaml.safe_load(f)
                    info(f"📁 本地加载下游配置: {config_name} ({declared_id}) <- {path}")
                
                # 验证ID一致性
                file_id = downstream_config.get("id")
                if file_id != declared_id:
                    raise ValueError(
                        f"下游配置ID不匹配: 声明ID='{declared_id}', 文件ID='{file_id}'"
                    )
                
                self._validate_downstream_config(downstream_config)
                
                downstream_config["_metadata"] = {
                    "source": source,
                    "name": config_name,
                    "loaded_from": config_def.get("path", config_def.get("url")),
                    "required": config_def.get("required", False)
                }
                
                downstreams.append(downstream_config)
                
            except Exception as e:
                error_msg = f"❌ 加载下游配置失败 {declared_id}: {e}"
                error(error_msg)
                
                if config_def.get("required", False):
                    raise Exception(error_msg) from e
                
                continue
        
        return downstreams
    
    def _validate_upstream_config(self, config: Dict[str, Any]) -> None:
        """验证上游配置"""
        required_fields = ["id", "adapters"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise ValueError(f"上游配置缺少必要字段: {', '.join(missing_fields)}")
        
        upstream_id = config["id"]
        if not upstream_id or not isinstance(upstream_id, str):
            raise ValueError("上游ID必须是非空字符串")
    
    def _validate_downstream_config(self, config: Dict[str, Any]) -> None:
        """验证下游配置"""
        required_fields = ["id"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise ValueError(f"下游配置缺少必要字段: {', '.join(missing_fields)}")
        
        downstream_id = config["id"]
        if not downstream_id or not isinstance(downstream_id, str):
            raise ValueError("下游ID必须是非空字符串")
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """验证最终配置"""
        # 检查路由引用的上游是否都已加载
        loaded_upstream_ids = {up["id"] for up in config["upstreams"]}
        
        for route in config["routes"]:
            # 检查规则中的上游
            for rule in route.get("rules", []):
                upstream_id = rule.get("upstream")
                if upstream_id and upstream_id not in loaded_upstream_ids:
                    raise ValueError(
                        f"路由引用了未加载的上游: {upstream_id}\n"
                        f"已加载的上游: {', '.join(sorted(loaded_upstream_ids))}"
                    )
            
            # 检查兜底上游
            fallback_upstream = route.get("fallback_upstream")
            if fallback_upstream and fallback_upstream not in loaded_upstream_ids:
                raise ValueError(
                    f"兜底路由引用了未加载的上游: {fallback_upstream}\n"
                    f"已加载的上游: {', '.join(sorted(loaded_upstream_ids))}"
                )
        
        info(f"✅ 配置验证通过: {len(loaded_upstream_ids)} 个上游已加载")
    
    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


def load_config() -> Dict[str, Any]:
    """
    统一配置加载器
    
    优先级:
    1. 环境变量 CONFIG_DIR 指定的配置目录
    2. 默认配置目录 ./config
    3. 环境变量 MAIN_CONFIG_URL 指定的远程主配置
    
    如果都不存在则抛出异常
    """
    # 检查环境变量指定的配置目录
    config_dir = os.getenv("CONFIG_DIR")
    if config_dir:
        config_path = Path(config_dir)
        if config_path.exists() and config_path.is_dir():
            info(f"📁 使用环境变量指定的配置目录: {config_dir}")
            loader = MultiConfigLoader(local_config_dir=config_dir)
            return loader.load_config()
        else:
            raise FileNotFoundError(f"环境变量 CONFIG_DIR 指定的目录不存在: {config_dir}")
    
    # 检查默认配置目录
    default_config_dir = Path("./config")
    if default_config_dir.exists() and (default_config_dir / "main.yaml").exists():
        info("📁 使用默认配置目录: ./config")
        loader = MultiConfigLoader(local_config_dir=str(default_config_dir))
        return loader.load_config()
    
    # 检查是否有远程主配置URL
    main_config_url = os.getenv("MAIN_CONFIG_URL")
    if main_config_url:
        info(f"📥 使用远程主配置: {main_config_url}")
        loader = MultiConfigLoader(main_config_url=main_config_url)
        return loader.load_config()
    
    # 都不存在，抛出异常
    raise FileNotFoundError(
        "未找到配置文件！请确保：\n"
        "1. 设置环境变量 CONFIG_DIR 指向配置目录\n"
        "2. 或者在当前目录下存在 ./config/main.yaml 文件\n"
        "3. 或者设置环境变量 MAIN_CONFIG_URL 指向远程主配置文件"
    )


# 全局配置对象
CONFIG = load_config()