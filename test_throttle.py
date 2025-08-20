#!/usr/bin/env python3
"""测试扣量功能的稳定性"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from services.router import calculate_throttle_score, should_throttle_callback
import uuid


def test_throttle_stability():
    """测试扣量算法的稳定性"""
    print("=== 测试扣量算法稳定性 ===")
    
    # 生成一些测试 RID
    test_rids = [str(uuid.uuid4()) for _ in range(5)]
    
    for rid in test_rids:
        print(f"\nRID: {rid}")
        
        # 计算哈希评分
        score = calculate_throttle_score(rid)
        print(f"  哈希评分: {score:.6f}")
        
        # 测试不同扣量比例
        for throttle_rate in [0.0, 0.2, 0.5, 0.8, 1.0]:
            result = should_throttle_callback(rid, throttle_rate)
            print(f"  扣量比例 {throttle_rate}: {'拦截' if result else '放行'}")
        
        # 验证多次调用结果一致
        results = [should_throttle_callback(rid, 0.3) for _ in range(5)]
        consistent = len(set(results)) == 1
        print(f"  多次调用一致性 (0.3): {consistent} - {results[0]}")


def test_throttle_distribution():
    """测试扣量分布是否均匀"""
    print("\n=== 测试扣量分布均匀性 ===")
    
    # 生成大量 RID 测试分布
    rids = [str(uuid.uuid4()) for _ in range(1000)]
    throttle_rate = 0.2  # 20% 扣量
    
    throttled_count = sum(1 for rid in rids if should_throttle_callback(rid, throttle_rate))
    actual_rate = throttled_count / len(rids)
    
    print(f"预期扣量比例: {throttle_rate}")
    print(f"实际扣量比例: {actual_rate:.3f}")
    print(f"扣量数量: {throttled_count}/{len(rids)}")
    print(f"误差: {abs(actual_rate - throttle_rate):.3f}")


if __name__ == "__main__":
    test_throttle_stability()
    test_throttle_distribution()
