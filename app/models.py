from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, JSON, Index
from .db import Base

class RequestLog(Base):
    """统一请求表 - 合并 track 与 callback，记录必要列及URL"""
    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rid: Mapped[str] = mapped_column(String(36), unique=True, index=True)  # 回调关联ID（等于trace_id）
    ds_id: Mapped[str] = mapped_column(String(64), index=True)
    up_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(16))  # click/imp
    ad_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    ts: Mapped[int] = mapped_column(BigInteger)  # 毫秒
    os: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # 原始参数
    upload_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)      # 上报收到的原始参数
    callback_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # 回调收到的原始参数

    # URL 记录
    upstream_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)    # 上报上游最终URL
    downstream_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)  # 最终回拨下游URL

    # 时间字段
    track_time: Mapped[str | None] = mapped_column(String(32), nullable=True)  # track创建时间（上海时区）

    # 回调状态
    is_callback_sent: Mapped[int] = mapped_column(Integer, default=0)  # 0/1
    callback_time: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 回调时间（上海时区）
    callback_event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

# 索引
Index("idx_req_ds_ad", RequestLog.ds_id, RequestLog.ad_id)
