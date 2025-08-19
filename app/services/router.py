from typing import Dict, Any, Tuple, Optional

def choose_route(udm: Dict[str, Any], config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    根据UDM数据和路由配置选择上游和下游
    
    Args:
        udm: 统一数据模型
        config: 全局配置
    
    Returns:
        (upstream_id, downstream_id) 元组，可能为None
    """
    rules = config.get("routes", [])
    if not rules:
        return None, None
    
    # 提取路由关键字段
    ad_info = udm.get("ad", {})
    campaign_id = ad_info.get("campaign_id", "")
    ad_id = ad_info.get("ad_id", "")
    
    # 遍历路由规则
    for rule in rules:
        match_key = rule.get("match_key", "")
        rule_list = rule.get("rules", [])
        
        # 按campaign_id匹配
        if match_key == "campaign_id" and campaign_id:
            for r in rule_list:
                if r.get("equals") == campaign_id:
                    return r.get("upstream"), r.get("downstream")
        
        # 按ad_id匹配
        elif match_key == "ad_id" and ad_id:
            for r in rule_list:
                if r.get("equals") == ad_id:
                    return r.get("upstream"), r.get("downstream")
        
        # 可以扩展更多匹配规则，如：
        # - 按下游ID匹配
        # - 按地域匹配
        # - 按设备类型匹配
        # - 按时间段匹配
        # - 权重分配等
    
    # 未匹配到具体规则，使用兜底配置
    if rules:
        first_rule = rules[0]
        fallback_upstream = first_rule.get("fallback_upstream")
        fallback_downstream = first_rule.get("fallback_downstream")
        return fallback_upstream, fallback_downstream
    
    return None, None

def find_upstream_config(upstream_id: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """查找上游配置"""
    if not upstream_id:
        return None
    
    upstreams = config.get("upstreams", [])
    for upstream in upstreams:
        if upstream.get("id") == upstream_id:
            return upstream
    
    return None

def find_downstream_config(downstream_id: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """查找下游配置"""
    if not downstream_id:
        return None
    
    downstreams = config.get("downstreams", [])
    for downstream in downstreams:
        if downstream.get("id") == downstream_id:
            return downstream
    
    return None

def get_adapter_config(partner_config: Dict[str, Any], adapter_type: str, event_type: str) -> Optional[Dict[str, Any]]:
    """
    获取适配器配置
    
    Args:
        partner_config: 合作方配置（上游或下游）
        adapter_type: 适配器类型（outbound, inbound_callback, outbound_callback等）
        event_type: 事件类型（click, imp, event等）
    
    Returns:
        适配器配置字典或None
    """
    adapters = partner_config.get("adapters", {})
    adapter_group = adapters.get(adapter_type, {})
    return adapter_group.get(event_type)
