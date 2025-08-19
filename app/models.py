from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, JSON, Index, UniqueConstraint
from .db import Base

class EventLog(Base):
    """事件日志表 - 记录所有上报事件"""
    __tablename__ = "event_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(8), index=True)  # YYYYMMDD
    trace_id: Mapped[str] = mapped_column(String(36), index=True)  # 链路追踪ID
    ds_id: Mapped[str] = mapped_column(String(64), index=True)  # 下游ID
    up_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 上游ID
    event_type: Mapped[str] = mapped_column(String(16))  # click/imp
    click_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # 点击ID
    ad_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # 广告ID
    ts: Mapped[int] = mapped_column(BigInteger)  # 时间戳（毫秒）
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)  # IP地址
    ua: Mapped[str | None] = mapped_column(String(512), nullable=True)  # User-Agent
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 原始载荷
    
    # 唯一约束：同一天内同一下游的同一事件类型和点击ID只能记录一次（幂等）
    __table_args__ = (
        UniqueConstraint("day", "ds_id", "event_type", "click_id", name="uniq_day_ds_evt_click"),
    )

class DispatchLog(Base):
    """分发日志表 - 记录向上游/下游的HTTP请求"""
    __tablename__ = "dispatch_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(8), index=True)  # YYYYMMDD
    trace_id: Mapped[str] = mapped_column(String(36), index=True)  # 链路追踪ID
    direction: Mapped[str] = mapped_column(String(16))  # to_upstream / to_downstream
    partner_id: Mapped[str] = mapped_column(String(64), index=True)  # 合作方ID
    endpoint: Mapped[str] = mapped_column(String(256))  # 请求端点
    method: Mapped[str] = mapped_column(String(8))  # HTTP方法
    status: Mapped[int] = mapped_column(Integer)  # HTTP状态码
    req: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 请求数据
    resp: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 响应数据

class CallbackLog(Base):
    """回调日志表 - 记录上游回调处理"""
    __tablename__ = "callback_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(8), index=True)  # YYYYMMDD
    trace_id: Mapped[str] = mapped_column(String(36), index=True)  # 链路追踪ID
    up_id: Mapped[str] = mapped_column(String(64))  # 上游ID
    ds_id: Mapped[str] = mapped_column(String(64))  # 下游ID
    ok: Mapped[int] = mapped_column(Integer)  # 处理是否成功 1/0
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 原始数据

# 创建额外索引以提高查询性能
Index("idx_event_click", EventLog.click_id)

Index("idx_dispatch_partner", DispatchLog.partner_id)
Index("idx_callback_up_ds", CallbackLog.up_id, CallbackLog.ds_id)
