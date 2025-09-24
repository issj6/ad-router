import os
from typing import Optional, Dict, Tuple
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# 自动加载.env文件
try:
    from dotenv import load_dotenv
    load_dotenv()  # 加载项目根目录的.env文件
except ImportError:
    # 如果没有安装python-dotenv，给出提示
    pass

Base = declarative_base()

# 进程级 MySQL 异步引擎与会话（避免跨进程共享状态）
_engines: Dict[int, AsyncEngine] = {}
_session_factories: Dict[int, async_sessionmaker[AsyncSession]] = {}

# 从环境变量获取数据库配置，确保安全性
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

# 验证必需的环境变量
if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB]):
    missing_vars = []
    if not MYSQL_HOST: missing_vars.append("MYSQL_HOST")
    if not MYSQL_USER: missing_vars.append("MYSQL_USER")
    if not MYSQL_PASSWORD: missing_vars.append("MYSQL_PASSWORD")
    if not MYSQL_DB: missing_vars.append("MYSQL_DB")
    
    raise ValueError(
        f"Missing required database environment variables: {', '.join(missing_vars)}\n"
        "\nPlease set them using one of these methods:\n"
        "1. Create a .env file in project root with:\n"
        "   MYSQL_HOST=your_host\n"
        "   MYSQL_USER=your_user\n"
        "   MYSQL_PASSWORD=your_password\n"
        "   MYSQL_DB=your_database\n"
        "\n2. Export environment variables:\n"
        "   export MYSQL_HOST=your_host\n"
        "   export MYSQL_USER=your_user\n"
        "   export MYSQL_PASSWORD=your_password\n"
        "   export MYSQL_DB=your_database\n"
        "\n3. Use Docker with --env-file .env"
    )

async def _prepare_engine() -> AsyncEngine:
    """创建进程级 MySQL 异步引擎（asyncmy）"""
    # 使用 asyncmy 驱动以获得更好的性能
    dsn = f"mysql+asyncmy://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
    engine = create_async_engine(
        dsn,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=1800,   # 30分钟回收
        pool_size=10,        # 减少每进程连接数
        max_overflow=20,     # 减少每进程溢出连接数
    )
    # 初始化表结构
    async with engine.begin() as conn:
        from .models import RequestLog
        await conn.run_sync(Base.metadata.create_all)
    return engine

async def get_session() -> AsyncSession:
    """获取进程级 MySQL 会话（异步）"""
    global _engines, _session_factories
    pid = os.getpid()
    
    if pid not in _engines:
        _engines[pid] = await _prepare_engine()
        _session_factories[pid] = async_sessionmaker(_engines[pid], expire_on_commit=False)
    
    return _session_factories[pid]()

async def cleanup_old_engines():
    """清理当前进程的数据库连接"""
    global _engines, _session_factories
    pid = os.getpid()
    
    if pid in _engines:
        await _engines[pid].dispose()
        del _engines[pid]
        del _session_factories[pid]
