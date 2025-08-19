#!/usr/bin/env python3
"""
OCPX中转系统测试示例
"""

import requests
import json
import time
import hashlib
import hmac

# 配置
BASE_URL = "http://localhost:8000"
DS_ID = "ds_demo"
CAMPAIGN_ID = "cmp_456"

def test_health():
    """测试健康检查"""
    print("🔍 测试健康检查...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

def test_click():
    """测试点击上报"""
    print("🔍 测试点击上报...")
    
    data = {
        "ds_id": DS_ID,
        "event_type": "click",
        "campaign_id": CAMPAIGN_ID,
        "click_id": f"test_click_{int(time.time())}",
        "ts": int(time.time()),
        "ip": "1.2.3.4",
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        "device": {
            "idfa": "ABCD-1234-EFGH-5678",
            "os": "iOS",
            "os_version": "14.0"
        },
        "ext": {
            "test": True
        }
    }
    
    response = requests.get(
        f"{BASE_URL}/v1/track",
        params={
            "event_type": "click",
            "ds_id": DS_ID,
            "campaign_id": CAMPAIGN_ID,
            "click_id": data["click_id"],
            "ts": data["ts"],
            "ip": data["ip"],
            "ua": data["ua"],
            "device_os": data["device"]["os"],
            "device_idfa": data["device"]["idfa"]
        }
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()
    
    return response.json().get("data", {}).get("click_id")

def test_imp():
    """测试曝光上报"""
    print("🔍 测试曝光上报...")
    
    data = {
        "ds_id": DS_ID,
        "event_type": "imp",
        "campaign_id": CAMPAIGN_ID,
        "ts": int(time.time()),
        "device": {
            "idfa": "ABCD-1234-EFGH-5678"
        }
    }
    
    response = requests.get(
        f"{BASE_URL}/v1/track",
        params={
            "event_type": "imp",
            "ds_id": DS_ID,
            "campaign_id": CAMPAIGN_ID,
            "ts": data["ts"],
            "device_os": "iOS",
            "device_idfa": "ABCD-1234-EFGH-5678"
        }
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

def test_event(click_id):
    """测试转化事件上报"""
    print("🔍 测试转化事件上报...")
    
    data = {
        "ds_id": DS_ID,
        "event_type": "event",
        "event_name": "install",
        "click_id": click_id,
        "campaign_id": CAMPAIGN_ID,
        "ts": int(time.time())
    }
    
    response = requests.get(
        f"{BASE_URL}/v1/track",
        params={
            "event_type": "event",
            "event_name": "install",
            "ds_id": DS_ID,
            "campaign_id": CAMPAIGN_ID,
            "click_id": click_id,
            "ts": data["ts"]
        }
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

def test_callback_simulation():
    """模拟上游回调测试"""
    print("🔍 模拟上游回调测试...")
    print("注意: 这需要从实际的上游请求响应中获取回调token")
    print("请查看上游请求的日志或httpbin响应中的cb参数")
    print()

def test_duplicate():
    """测试幂等性"""
    print("🔍 测试幂等性...")
    
    click_id = f"duplicate_test_{int(time.time())}"
    
    data = {
        "ds_id": DS_ID,
        "event_type": "click",
        "campaign_id": CAMPAIGN_ID,
        "click_id": click_id,
        "ts": int(time.time())
    }
    
    # 第一次请求
    print("第一次请求:")
    response1 = requests.get(
        f"{BASE_URL}/v1/track",
        params={
            "event_type": "click",
            "ds_id": DS_ID,
            "campaign_id": CAMPAIGN_ID,
            "click_id": click_id,
            "ts": data["ts"]
        }
    )
    print(f"状态码: {response1.status_code}")
    print(f"响应: {response1.json()}")
    
    # 第二次请求（重复）
    print("第二次请求（重复）:")
    response2 = requests.get(
        f"{BASE_URL}/v1/track",
        params={
            "event_type": "click",
            "ds_id": DS_ID,
            "campaign_id": CAMPAIGN_ID,
            "click_id": click_id,
            "ts": data["ts"]
        }
    )
    print(f"状态码: {response2.status_code}")
    print(f"响应: {response2.json()}")
    print()

def main():
    print("🚀 OCPX中转系统测试开始...")
    print(f"测试地址: {BASE_URL}")
    print("=" * 50)
    
    try:
        # 健康检查
        test_health()
        
        # 点击上报
        click_id = test_click()
        
        # 曝光上报
        test_imp()
        
        # 转化事件上报
        if click_id:
            test_event(click_id)
        
        # 幂等性测试
        test_duplicate()
        
        # 回调模拟说明
        test_callback_simulation()
        
        print("✅ 所有测试完成!")
        print("\n📋 后续步骤:")
        print("1. 查看服务日志，确认上游请求是否正常发送")
        print("2. 检查 ./data/sqlite/ 目录下的数据库文件")
        print("3. 访问 http://localhost:8000/docs 查看API文档")
        print("4. 根据实际需求修改 config.yaml 配置")
        
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败，请确认服务是否已启动")
        print("启动命令: python start.py")
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    main()
