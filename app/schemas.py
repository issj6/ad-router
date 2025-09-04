from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, Optional

class TrackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "ds_id": "ds_demo",
            "event_type": "click",
            "ad_id": "ad_123",
            "channel_id": "ch_01",
            "ts": 1734508800000,
            "ip": "1.2.3.4",
            "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            "device": {
                "idfa": "ABCD-1234-EFGH-5678",
                "os": "iOS",
                "os_version": "14.0",
                "model": "iPhone12,1"
            },
            "ext": {
                "custom_id": "xyz_001"
            }
        }
    })

    """统一上报请求模型（仅 click/imp），广告只保留 ad_id"""
    ds_id: str = Field(..., description="下游ID，用于标识请求来源")
    event_type: str = Field(..., description="事件类型：click/imp")

    # 广告相关字段
    ad_id: str = Field(..., description="广告ID")
    channel_id: Optional[str] = Field(None, description="渠道ID")



    # 时间和网络字段
    ts: Optional[int] = Field(None, description="时间戳（毫秒），不传则使用服务器时间")
    ip: Optional[str] = Field(None, description="用户IP地址")
    ua: Optional[str] = Field(None, description="User-Agent")

    # 设备信息
    device: Optional[Dict[str, Any]] = Field(None, description="设备信息，如：{\"idfa\":\"xxx\",\"os\":\"iOS\",\"os_version\":\"14.0\",\"mac\":\"00:11:22:33:44:55\"}")

    # 用户信息（仅接受哈希值）
    user: Optional[Dict[str, Any]] = Field(None, description="用户信息，如：{\"phone_md5\":\"xxx\",\"email_sha256\":\"xxx\"}")

    # 扩展字段
    ext: Optional[Dict[str, Any]] = Field(None, description="扩展字段，任意键值对")



class APIResponse(BaseModel):
    """统一响应模型：仅 success / code / message"""
    success: bool = Field(..., description="是否成功")
    code: int = Field(..., description="状态码：200=成功；失败与HTTP状态码一致")
    message: str = Field(..., description="描述信息")

class HealthResponse(BaseModel):
    """健康检查响应模型"""
    ok: bool = Field(..., description="服务是否正常")
    timestamp: int = Field(..., description="当前时间戳")
    version: str = Field(..., description="服务版本")
    db_ok: Optional[bool] = Field(None, description="数据库连接状态")
    debounce_ok: Optional[bool] = Field(None, description="去抖管理器运行状态")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "ok": True,
            "timestamp": 1734508800,
            "version": "1.0.0",
            "db_ok": True,
            "debounce_ok": True
        }
    })
