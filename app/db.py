import os
import datetime
import asyncio
from typing import Dict
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import text

Base = declarative_base()

# 缓存每日数据库引擎和会话
_engines: Dict[str, AsyncEngine] = {}
_sessions: Dict[str, async_sessionmaker[AsyncSession]] = {}

def _today_key() -> str:
    """获取今日日期键 YYYYMMDD"""
    return datetime.datetime.now().strftime("%Y%m%d")

async def _prepare_engine(db_path: str) -> AsyncEngine:
    """准备数据库引擎，设置WAL模式以提高并发性能"""
    # 确保目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 创建异步引擎
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", 
        echo=False, 
        pool_pre_ping=True,
        pool_recycle=3600  # 1小时回收连接
    )
    
    # 设置SQLite优化参数
    async with engine.begin() as conn:
        # WAL 模式，提高并发读写性能
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        # 正常同步模式，平衡性能和安全
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        # 设置缓存大小
        await conn.execute(text("PRAGMA cache_size=10000;"))
        # 设置临时存储为内存
        await conn.execute(text("PRAGMA temp_store=memory;"))
    
    return engine

async def get_session() -> AsyncSession:
    """获取当日数据库会话"""
    key = _today_key()
    
    if key not in _sessions:
        # 构建当日数据库路径
        from .config import CONFIG
        db_path = os.path.join(
            CONFIG["settings"]["data_dir"],
            f"{key}.db"
        )
        
        # 创建引擎
        engine = await _prepare_engine(db_path)
        _engines[key] = engine
        _sessions[key] = async_sessionmaker(engine, expire_on_commit=False)
        
        # 初始化表结构
        async with engine.begin() as conn:
            # 导入模型以确保表定义被加载
            from .models import EventLog, DispatchLog, CallbackLog
            await conn.run_sync(Base.metadata.create_all)
    
    return _sessions[key]()

async def cleanup_old_engines():
    """清理旧的数据库引擎（可选的维护任务）"""
    current_key = _today_key()
    keys_to_remove = []
    
    for key in _engines.keys():
        if key != current_key:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        if key in _engines:
            await _engines[key].dispose()
            del _engines[key]
        if key in _sessions:
            del _sessions[key]
