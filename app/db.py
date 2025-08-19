import os
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 全局 MySQL 异步引擎与会话
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

# 默认使用你提供的连接信息；也支持通过环境变量覆盖
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
MYSQL_DB = os.getenv("MYSQL_DB", "ad_router")

async def _prepare_engine() -> AsyncEngine:
    """创建全局 MySQL 异步引擎（aiomysql）"""
    # 使用 asyncmy 驱动以获得更好的性能
    dsn = f"mysql+asyncmy://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
    engine = create_async_engine(
        dsn,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=1800,   # 30分钟回收
        pool_size=20,
        max_overflow=40,
    )
    # 初始化表结构
    async with engine.begin() as conn:
        from .models import RequestLog
        await conn.run_sync(Base.metadata.create_all)
    return engine

async def get_session() -> AsyncSession:
    """获取全局 MySQL 会话（异步）"""
    global _engine, _session_factory
    if _engine is None:
        _engine = await _prepare_engine()
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    assert _session_factory is not None
    return _session_factory()

async def cleanup_old_engines():
    """兼容保留，无需处理（MySQL 单实例）"""
    return
