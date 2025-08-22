#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
在线配置检查脚本

功能：
- 下载在线配置 https://gitee.com/yang0000111/files/raw/master/ad-router-config.yaml
- 校验配置结构(settings/upstreams/routes)
- 按 ad_id=67576 模拟 choose_route 选择结果
- 输出为什么会出现“链接已关闭”的诊断结论
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


ONLINE_URL = "https://gitee.com/yang0000111/files/raw/master/ad-router-config.yaml"


def download_config(url: str) -> Dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = yaml.safe_load(resp.text)
        assert isinstance(data, dict), "配置根节点必须是字典"
        for key in ("settings", "upstreams", "routes"):
            assert key in data, f"配置缺少必要字段: {key}"
        if "downstreams" not in data:
            data["downstreams"] = []
        return data


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
    print(f"下载在线配置: {ONLINE_URL}")
    cfg = download_config(ONLINE_URL)
    print("配置加载成功\n")

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
        print("\n诊断：配置看起来正确，若仍返回400，请检查运行实例是否已拉取最新配置或查看应用日志中的[to-upstream]输出。")


if __name__ == "__main__":
    ad = sys.argv[1] if len(sys.argv) > 1 else "67576"
    main(ad)





