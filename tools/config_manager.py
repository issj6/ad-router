#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多文件配置管理工具

功能:
- 将单文件配置拆分为多文件
- 验证多文件配置
- 合并多文件配置为单文件
- 添加新的上游配置
"""

import sys
import yaml
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class ConfigManager:
    """配置管理器"""
    
    def split_config(self, source_file: str, output_dir: str) -> None:
        """将单文件配置拆分为多文件"""
        source_path = Path(source_file)
        output_path = Path(output_dir)
        
        if not source_path.exists():
            raise FileNotFoundError(f"源配置文件不存在: {source_file}")
        
        # 创建目录结构
        (output_path / "upstreams").mkdir(parents=True, exist_ok=True)
        (output_path / "downstreams").mkdir(parents=True, exist_ok=True)
        
        # 加载源配置
        with open(source_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        print(f"📄 正在拆分配置文件: {source_file}")
        
        # 拆分上游配置
        upstreams = config.get("upstreams", [])
        upstream_configs = []
        
        for upstream in upstreams:
            upstream_id = upstream["id"]
            upstream_name = upstream.get("name", upstream_id)
            upstream_file = output_path / "upstreams" / f"{upstream_id}.yaml"
            
            # 写入上游配置文件
            with open(upstream_file, 'w', encoding='utf-8') as f:
                yaml.dump(upstream, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            # 记录配置引用（包含ID和名称）
            upstream_configs.append({
                "id": upstream_id,
                "name": upstream_name,
                "source": "local",
                "path": f"upstreams/{upstream_id}.yaml",
                "required": True,  # 默认标记为必需
                "enabled": True    # 默认启用
            })
            
            print(f"  ✅ 创建上游配置: {upstream_file}")
        
        # 拆分下游配置（如果有）
        downstreams = config.get("downstreams", [])
        downstream_configs = []
        
        for downstream in downstreams:
            downstream_id = downstream["id"]
            downstream_name = downstream.get("name", downstream_id)
            downstream_file = output_path / "downstreams" / f"{downstream_id}.yaml"
            
            with open(downstream_file, 'w', encoding='utf-8') as f:
                yaml.dump(downstream, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            downstream_configs.append({
                "id": downstream_id,
                "name": downstream_name,
                "source": "local",
                "path": f"downstreams/{downstream_id}.yaml",
                "required": True,
                "enabled": True
            })
            
            print(f"  ✅ 创建下游配置: {downstream_file}")
        
        # 创建主配置文件
        main_config = {
            "settings": config.get("settings", {}),
            "upstream_configs": upstream_configs,
            "downstream_configs": downstream_configs,
            "routes": config.get("routes", [])
        }
        
        main_file = output_path / "main.yaml"
        with open(main_file, 'w', encoding='utf-8') as f:
            yaml.dump(main_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"\n✅ 配置拆分完成:")
        print(f"   主配置: {main_file}")
        print(f"   上游配置: {len(upstream_configs)} 个")
        for uc in upstream_configs:
            print(f"     - {uc['id']}: {uc['name']}")
        if downstream_configs:
            print(f"   下游配置: {len(downstream_configs)} 个")
            for dc in downstream_configs:
                print(f"     - {dc['id']}: {dc['name']}")
        print(f"\n📖 使用方法:")
        print(f"   export CONFIG_DIR={output_path.absolute()}")
        print(f"   python app/main.py")
    
    def validate_config(self, config_dir: str) -> bool:
        """验证多文件配置"""
        try:
            from app.config import MultiConfigLoader
            
            print(f"🔍 正在验证多文件配置: {config_dir}")
            loader = MultiConfigLoader(local_config_dir=config_dir)
            config = loader.load_config()
            
            print("✅ 配置验证通过")
            print(f"   设置: {len(config.get('settings', {}))} 项")
            print(f"   上游: {len(config.get('upstreams', []))} 个")
            print(f"   下游: {len(config.get('downstreams', []))} 个")
            print(f"   路由: {len(config.get('routes', []))} 条")
            
            # 显示加载的上游详情
            if config.get('upstreams'):
                print("\n📋 已加载的上游:")
                for upstream in config['upstreams']:
                    metadata = upstream.get('_metadata', {})
                    print(f"   - {upstream['id']}: {metadata.get('name', upstream['id'])}")
                    print(f"     来源: {metadata.get('source', 'unknown')} <- {metadata.get('loaded_from', 'unknown')}")
            
            return True
            
        except Exception as e:
            print(f"❌ 配置验证失败: {e}")
            return False
    
    def merge_config(self, config_dir: str, output_file: str) -> None:
        """合并多文件配置为单文件"""
        try:
            from app.config import MultiConfigLoader
            
            print(f"🔄 正在合并多文件配置: {config_dir}")
            loader = MultiConfigLoader(local_config_dir=config_dir)
            config = loader.load_config()
            
            # 清理元数据
            for upstream in config.get('upstreams', []):
                upstream.pop('_metadata', None)
            for downstream in config.get('downstreams', []):
                downstream.pop('_metadata', None)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            print(f"✅ 配置合并完成: {output_file}")
            
        except Exception as e:
            print(f"❌ 配置合并失败: {e}")
            raise
    
    def add_upstream(self, config_dir: str, upstream_id: str, upstream_name: str = None, template: str = "basic") -> None:
        """添加新的上游配置"""
        config_path = Path(config_dir)
        upstream_file = config_path / "upstreams" / f"{upstream_id}.yaml"
        main_file = config_path / "main.yaml"
        
        if upstream_file.exists():
            print(f"❌ 上游配置已存在: {upstream_file}")
            return
        
        if not main_file.exists():
            print(f"❌ 主配置文件不存在: {main_file}")
            return
        
        # 创建上游配置模板
        templates = {
            "basic": {
                "id": upstream_id,
                "name": upstream_name or upstream_id,
                "description": f"{upstream_name or upstream_id} 广告平台",
                "secrets": {
                    "secret": f"{upstream_id}_secret_key"
                },
                "adapters": {
                    "outbound": {
                        "click": {
                            "method": "GET",
                            "url": f"https://api.{upstream_id}.com/click?aid={{{{aid}}}}&ts={{{{ts}}}}&callback={{{{callback}}}}",
                            "macros": {
                                "aid": "udm.ad.ad_id | url_encode()",
                                "ts": "udm.time.ts",
                                "callback": "cb_url() | url_encode()"
                            },
                            "timeout_ms": 3000,
                            "retry": {"max": 2, "backoff_ms": 500}
                        }
                    },
                    "inbound_callback": {
                        "event": {
                            "source": "query",
                            "field_map": {
                                "udm.event.type": "const:event",
                                "udm.event.name": "query.event_type",
                                "udm.time.ts": "now_ms()"
                            }
                        }
                    }
                }
            }
        }
        
        upstream_config = templates.get(template, templates["basic"])
        
        # 写入上游配置文件
        upstream_file.parent.mkdir(exist_ok=True)
        with open(upstream_file, 'w', encoding='utf-8') as f:
            yaml.dump(upstream_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # 更新主配置文件
        with open(main_file, 'r', encoding='utf-8') as f:
            main_config = yaml.safe_load(f)
        
        upstream_configs = main_config.get("upstream_configs", [])
        upstream_configs.append({
            "id": upstream_id,
            "name": upstream_name or upstream_id,
            "source": "local",
            "path": f"upstreams/{upstream_id}.yaml",
            "required": True,
            "enabled": True
        })
        
        main_config["upstream_configs"] = upstream_configs
        
        with open(main_file, 'w', encoding='utf-8') as f:
            yaml.dump(main_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"✅ 新上游配置已添加:")
        print(f"   配置文件: {upstream_file}")
        print(f"   上游ID: {upstream_id}")
        print(f"   显示名: {upstream_name or upstream_id}")
        print(f"\n📝 下一步:")
        print(f"   1. 编辑 {upstream_file} 完善配置")
        print(f"   2. 在 {main_file} 的 routes 中添加路由规则")
    
    def list_upstreams(self, config_dir: str) -> None:
        """列出所有上游配置"""
        try:
            from app.config import MultiConfigLoader
            
            loader = MultiConfigLoader(local_config_dir=config_dir)
            config = loader.load_config()
            
            upstreams = config.get('upstreams', [])
            if not upstreams:
                print("❌ 没有找到上游配置")
                return
            
            print(f"📋 上游配置列表 ({len(upstreams)} 个):")
            for upstream in upstreams:
                metadata = upstream.get('_metadata', {})
                print(f"\n  🔗 {upstream['id']}")
                print(f"     名称: {metadata.get('name', upstream.get('name', upstream['id']))}")
                print(f"     描述: {upstream.get('description', '无')}")
                print(f"     来源: {metadata.get('source', 'unknown')}")
                print(f"     文件: {metadata.get('loaded_from', 'unknown')}")
                print(f"     必需: {'是' if metadata.get('required', False) else '否'}")
                
                # 显示支持的事件类型
                adapters = upstream.get('adapters', {})
                outbound = adapters.get('outbound', {})
                events = list(outbound.keys())
                if events:
                    print(f"     事件: {', '.join(events)}")
            
        except Exception as e:
            print(f"❌ 列出上游配置失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="多文件配置管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 拆分命令
    split_parser = subparsers.add_parser("split", help="拆分单文件配置")
    split_parser.add_argument("source", help="源配置文件")
    split_parser.add_argument("output", help="输出目录")
    
    # 验证命令
    validate_parser = subparsers.add_parser("validate", help="验证多文件配置")
    validate_parser.add_argument("config_dir", help="配置目录")
    
    # 合并命令
    merge_parser = subparsers.add_parser("merge", help="合并多文件配置")
    merge_parser.add_argument("config_dir", help="配置目录")
    merge_parser.add_argument("output", help="输出文件")
    
    # 添加上游命令
    add_parser = subparsers.add_parser("add-upstream", help="添加新的上游配置")
    add_parser.add_argument("config_dir", help="配置目录")
    add_parser.add_argument("upstream_id", help="上游ID")
    add_parser.add_argument("--name", help="上游显示名称")
    add_parser.add_argument("--template", choices=["basic"], default="basic", help="配置模板")
    
    # 列出上游命令
    list_parser = subparsers.add_parser("list", help="列出所有上游配置")
    list_parser.add_argument("config_dir", help="配置目录")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = ConfigManager()
    
    try:
        if args.command == "split":
            manager.split_config(args.source, args.output)
        elif args.command == "validate":
            success = manager.validate_config(args.config_dir)
            sys.exit(0 if success else 1)
        elif args.command == "merge":
            manager.merge_config(args.config_dir, args.output)
        elif args.command == "add-upstream":
            manager.add_upstream(args.config_dir, args.upstream_id, args.name, args.template)
        elif args.command == "list":
            manager.list_upstreams(args.config_dir)
        else:
            parser.print_help()
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
