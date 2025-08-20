#!/usr/bin/env python3
"""测试扣量状态设置"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from services.router import should_throttle_callback


def test_throttle_status():
    """测试不同rid的扣量状态"""
    print("=== 测试扣量状态设置 ===")
    
    # 测试一些 rid，找出会被扣量的
    test_rids = [
        "test-rid-001",
        "test-rid-002", 
        "test-rid-003",
        "11111111-1111-1111-1111-111111111111",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    ]
    
    throttle_rate = 0.5  # 50% 扣量，更容易找到被扣量的例子
    
    for rid in test_rids:
        is_throttled = should_throttle_callback(rid, throttle_rate)
        status = "被扣量 (status=2)" if is_throttled else "正常转发 (status=1)"
        print(f"RID: {rid} -> {status}")
    
    print("\n=== 状态说明 ===")
    print("0: 未回拨")
    print("1: 已成功回拨给下游")  
    print("2: 被扣量（拦截）")


if __name__ == "__main__":
    test_throttle_status()
