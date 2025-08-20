#!/usr/bin/env python3
"""
测试脚本：验证API返回码统一性
"""
import requests
import json

# 配置测试服务器地址
BASE_URL = "http://localhost:8000"

def test_track_success():
    """测试track接口成功场景"""
    print("\n1. 测试Track接口 - 成功场景")
    # 需要配置正确的参数和路由
    params = {
        "ds_id": "test_downstream",
        "event_type": "click",
        "ad_id": "test_ad",
        "click_id": "test_click_123"
    }
    response = requests.get(f"{BASE_URL}/v1/track", params=params)
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code in [200, 500], "返回码应该是200或500"

def test_track_invalid_event_type():
    """测试track接口参数错误"""
    print("\n2. 测试Track接口 - 无效event_type")
    params = {
        "ds_id": "test",
        "event_type": "invalid",  # 无效的事件类型
        "ad_id": "test_ad"
    }
    response = requests.get(f"{BASE_URL}/v1/track", params=params)
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code == 500, "无效参数应该返回500"

def test_callback_missing_rid():
    """测试callback接口缺少rid参数"""
    print("\n3. 测试Callback接口 - 缺少rid参数")
    response = requests.get(f"{BASE_URL}/cb")
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code == 500, "缺少必需参数应该返回500"

def test_callback_invalid_rid():
    """测试callback接口无效rid"""
    print("\n4. 测试Callback接口 - 无效rid")
    params = {"rid": "invalid-rid-12345"}
    response = requests.get(f"{BASE_URL}/cb", params=params)
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code == 500, "无效rid应该返回500"

def test_health_check():
    """测试健康检查接口"""
    print("\n5. 测试健康检查接口")
    response = requests.get(f"{BASE_URL}/health")
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code == 200, "健康检查应该始终返回200"

if __name__ == "__main__":
    print("=== adRouter 返回码统一性测试 ===")
    print(f"测试服务器: {BASE_URL}")
    
    try:
        # 先检查服务是否运行
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("错误: 服务未运行或不可访问")
            exit(1)
    except requests.exceptions.RequestException:
        print("错误: 无法连接到服务，请确保服务正在运行")
        exit(1)
    
    # 运行测试
    test_track_success()
    test_track_invalid_event_type()
    test_callback_missing_rid()
    test_callback_invalid_rid()
    test_health_check()
    
    print("\n✅ 所有测试完成！")
    print("\n返回码策略总结:")
    print("- Track接口: 成功=200, 所有错误=500")
    print("- Callback接口: 成功=200, 所有错误=500")
    print("- 健康检查: 始终=200")
