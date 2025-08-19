from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class TrackRequest(BaseModel):
    """统一上报请求模型"""
    ds_id: str = Field(..., description="下游ID，用于标识请求来源")
    event_type: str = Field(..., description="事件类型：click/imp/event")
    event_name: Optional[str] = Field(None, description="事件名称，event类型时使用，如：install/register/pay/retain")
    
    # 广告相关字段
    ad_id: Optional[str] = Field(None, description="广告ID")
    campaign_id: Optional[str] = Field(None, description="计划ID")
    adgroup_id: Optional[str] = Field(None, description="广告组ID")
    creative_id: Optional[str] = Field(None, description="创意ID")
    
    # 点击相关字段
    click_id: Optional[str] = Field(None, description="点击ID，click和event类型推荐必传")
    
    # 时间和网络字段
    ts: Optional[int] = Field(None, description="时间戳（秒），不传则使用服务器时间")
    ip: Optional[str] = Field(None, description="用户IP地址")
    ua: Optional[str] = Field(None, description="User-Agent")
    
    # 设备信息
    device: Optional[Dict[str, Any]] = Field(None, description="设备信息，如：{\"idfa\":\"xxx\",\"os\":\"iOS\"}")
    
    # 用户信息（仅接受哈希值）
    user: Optional[Dict[str, Any]] = Field(None, description="用户信息，如：{\"phone_md5\":\"xxx\",\"email_sha256\":\"xxx\"}")
    
    # 扩展字段
    ext: Optional[Dict[str, Any]] = Field(None, description="扩展字段，任意键值对")

    class Config:
        schema_extra = {
            "example": {
                "ds_id": "ds_demo",
                "event_type": "click",
                "campaign_id": "cmp_456",
                "click_id": "ck_abc123",
                "ts": 1734508800,
                "ip": "1.2.3.4",
                "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
                "device": {
                    "idfa": "ABCD-1234-EFGH-5678",
                    "os": "iOS",
                    "os_version": "14.0",
                    "model": "iPhone12,1"
                },
                "ext": {
                    "slot": "banner",
                    "position": "top"
                }
            }
        }

class TrackResponse(BaseModel):
    """统一上报响应模型"""
    code: int = Field(..., description="响应码：0=成功，其他=失败")
    msg: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")

    class Config:
        schema_extra = {
            "example": {
                "code": 0,
                "msg": "ok",
                "data": {
                    "trace_id": "12345678-1234-1234-1234-123456789abc",
                    "click_id": "ck_abc123",
                    "upstream_status": 200
                }
            }
        }

class CallbackResponse(BaseModel):
    """回调响应模型"""
    code: int = Field(..., description="响应码：0=成功，其他=失败")
    msg: str = Field(..., description="响应消息")

    class Config:
        schema_extra = {
            "example": {
                "code": 0,
                "msg": "ok"
            }
        }

class HealthResponse(BaseModel):
    """健康检查响应模型"""
    ok: bool = Field(..., description="服务是否正常")
    timestamp: Optional[int] = Field(None, description="当前时间戳")
    version: Optional[str] = Field(None, description="服务版本")

    class Config:
        schema_extra = {
            "example": {
                "ok": True,
                "timestamp": 1734508800,
                "version": "1.0.0"
            }
        }
