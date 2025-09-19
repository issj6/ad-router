#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置检查脚本

功能：
- 检查本地多文件配置结构
- 校验配置结构(settings/upstreams/routes)
- 按 ad_id=67576 模拟 choose_route 选择结果
- 输出诊断结论

注意：此脚本已更新为支持新的多文件配置架构
"""

import sys
import json
from typing import Any, Dict, Optional, Tuple

try:
    import httpx
    import yaml
except Exception as e:
    print("请先安装依赖: pip install httpx pyyaml")
    sys.exit(1)


def load_local_config() -> Dict[str, Any]:
    """加载本地多文件配置"""
    try:
        # 直接导入配置加载器
        import os
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app.config import CONFIG
        return CONFIG
    except Exception as e:
        print(f"❌ 加载本地配置失败: {e}")
        print("💡 请确保：")
        print("   1. config/main.yaml 文件存在")
        print("   2. 所有上游配置文件存在")
        print("   3. 环境变量配置正确（如需要）")
        sys.exit(1)


def choose_route_like(udm: Dict[str, Any], config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], bool, float]:
    rules = config.get("routes", [])
    if not rules:
        return None, None, False, 0.0

    ad_info = udm.get("ad", {})
    campaign_id = ad_info.get("campaign_id", "")
    ad_id = ad_info.get("ad_id", "")

    for rule in rules:
        match_key = rule.get("match_key", "")
        rule_list = rule.get("rules", [])

        if match_key == "campaign_id" and campaign_id:
            for r in rule_list:
                if r.get("equals") == campaign_id:
                    enabled = r.get("enabled", True)
                    throttle = r.get("throttle", 0.0)
                    return r.get("upstream"), r.get("downstream"), enabled, throttle
        elif match_key == "ad_id" and ad_id:
            for r in rule_list:
                if r.get("equals") == ad_id:
                    enabled = r.get("enabled", True)
                    throttle = r.get("throttle", 0.0)
                    return r.get("upstream"), r.get("downstream"), enabled, throttle

    # fallback
    if rules:
        first = rules[0]
        return (
            first.get("fallback_upstream"),
            first.get("fallback_downstream"),
            first.get("fallback_enabled", True),
            first.get("fallback_throttle", 0.0),
        )

    return None, None, False, 0.0


def main(ad_id: str = "67576"):
    print("🔍 加载本地多文件配置...")
    cfg = load_local_config()
    print("✅ 配置加载成功\n")

    # 打印关键段落
    print("routes 段落:")
    print(json.dumps(cfg.get("routes", []), ensure_ascii=False, indent=2))
    print()

    # 构造最小 UDM 进行匹配
    udm = {
        "ad": {"ad_id": ad_id},
        "event": {"type": "click"},
        "net": {"ip": "", "ua": ""},
        "time": {"ts": 0},
        "meta": {"downstream_id": "ow", "upstream_id": None, "ext": {}},
    }

    up_id, ds_out, enabled, throttle = choose_route_like(udm, cfg)

    print("匹配结果：")
    print(f"  upstream: {up_id}")
    print(f"  downstream: {ds_out}")
    print(f"  enabled: {enabled}")
    print(f"  throttle: {throttle}")

    # 诊断 “链接已关闭” 的可能原因
    problems = []
    if not up_id:
        problems.append("未匹配到具体规则，且未配置 fallback_upstream")
    if not enabled:
        problems.append("匹配命中但该规则 enabled=false 或 fallback_enabled=false")

    # 校验上游是否存在
    upstream_exists = False
    for up in cfg.get("upstreams", []):
        if up.get("id") == up_id:
            upstream_exists = True
            break
    if up_id and not upstream_exists:
        problems.append(f"上游 '{up_id}' 在 upstreams 中不存在")

    if problems:
        print("\n诊断：")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\n诊断：配置看起来正确，若仍返回400，请查看应用日志中的详细错误信息。")


if __name__ == "__main__":
    ad = sys.argv[1] if len(sys.argv) > 1 else "67576"
    main(ad)







