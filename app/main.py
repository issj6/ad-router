from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

from .routers.track import router as track_router
from .routers.callback import router as callback_router
from .schemas import HealthResponse
from .utils.logger import info, warning, error

# 初始化异步日志系统
from .utils.logger import setup_logger
setup_logger()

# 创建FastAPI应用
app = FastAPI(
    title="KPK API SERVER",
    description="",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件（如果需要跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(track_router, tags=["Track"])
app.include_router(callback_router, tags=["Callback"])

@app.get("/", response_model=HealthResponse)
async def root():
    """根路径 - 健康检查"""
    return HealthResponse(
        ok=True,
        timestamp=int(time.time()),
        version="1.0.0"
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口：附带数据库连通性检查"""
    db_ok = False
    debounce_ok = False
    redis_ok = False
    try:
        from .db import get_session
        from sqlalchemy import text
        import asyncio
        # 为健康检查的DB探测设置短超时，避免阻塞整个接口
        async def _probe_db():
            async with await get_session() as session:
                await session.execute(text("SELECT 1"))
        try:
            await asyncio.wait_for(_probe_db(), timeout=1.5)
            db_ok = True
        except asyncio.TimeoutError:
            warning("Database health probe timed out")
            db_ok = False
    except Exception as e:
        warning(f"Database connectivity check failed: {e}")
        db_ok = False

    # 去抖管理器状态检查
    try:
        # 仅当配置开启去抖时才检查/触碰 Redis，避免不必要的依赖导致健康检查变慢
        from .config import CONFIG
        debounce_enabled = bool(CONFIG.get("settings", {}).get("debounce", {}).get("enabled", False))
        if debounce_enabled:
            from .services.debounce_redis import get_manager
            mgr = get_manager()
            debounce_ok = getattr(mgr, "_running", False) is True
            # Redis ping 设置短超时
            import asyncio
            client = getattr(mgr, "_redis", None)
            if client is not None:
                async def _ping():
                    return await client.ping()
                try:
                    pong = await asyncio.wait_for(_ping(), timeout=0.5)
                    redis_ok = bool(pong)
                except asyncio.TimeoutError:
                    warning("Redis ping timed out")
                    redis_ok = False
                except Exception as re:
                    warning(f"Redis ping error: {re}")
                    redis_ok = False
        else:
            debounce_ok = False
            redis_ok = False
    except Exception as e:
        warning(f"Debounce manager health check failed: {e}")
        debounce_ok = False
        redis_ok = False
    return HealthResponse(
        ok=db_ok,  # 整体健康状态取决于数据库连接
        timestamp=int(time.time()),
        version="1.0.0",
        db_ok=db_ok,
        debounce_ok=debounce_ok,
        redis_ok=redis_ok
    )

@app.on_event("startup")
async def startup_event():
    """应用启动事件 - 每个进程独立初始化"""
    import os
    pid = os.getpid()
    info(f"OCPX Relay System starting up in process {pid}...")
    
    # 预热数据库连接（进程级）
    try:
        from .db import get_session
        async with await get_session() as session:
            info(f"Database connection preheated for process {pid}")
    except Exception as e:
        warning(f"Failed to preheat database connection: {e}")
    
    # 初始化去抖管理器（进程级）
    try:
        from .config import CONFIG
        debounce_enabled = bool(CONFIG.get("settings", {}).get("debounce", {}).get("enabled", False))
        if debounce_enabled:
            from .services.debounce_redis import get_manager
            await get_manager().start()
            info(f"Debounce manager started for process {pid}")
        else:
            info(f"Debounce disabled globally in process {pid}")
    except Exception as e:
        warning(f"Debounce manager failed to start in process {pid}: {e}")
    
    info(f"OCPX Relay System started successfully in process {pid}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件 - 每个进程独立清理"""
    import os
    pid = os.getpid()
    info(f"OCPX Relay System shutting down in process {pid}...")
    
    # 清理HTTP客户端（进程级）
    try:
        from .services.connector import cleanup_client
        await cleanup_client()
        info(f"HTTP client cleaned up for process {pid}")
    except Exception as e:
        warning(f"HTTP client cleanup failed in process {pid}: {e}")
    
    # 清理去抖管理器（进程级）
    try:
        from .config import CONFIG
        if bool(CONFIG.get("settings", {}).get("debounce", {}).get("enabled", False)):
            from .services.debounce_redis import get_manager
            mgr = get_manager()
            try:
                processed = await mgr.flush_all(force=True, max_items=500)  # 减少批量避免阻塞
                info(f"Debounce flush_all processed {processed} items in process {pid}")
            except Exception as fe:
                warning(f"Debounce flush_all failed in process {pid}: {fe}")
            await mgr.shutdown()
            info(f"Debounce manager shutdown in process {pid}")
        else:
            info(f"Debounce disabled, skip shutdown in process {pid}")
    except Exception as e:
        warning(f"Debounce manager shutdown failed in process {pid}: {e}")
    
    # 清理数据库连接（进程级）
    try:
        from .db import cleanup_old_engines
        await cleanup_old_engines()
        info(f"Database connections cleaned up for process {pid}")
    except Exception as e:
        warning(f"Database cleanup failed in process {pid}: {e}")
    
    info(f"OCPX Relay System shutdown complete in process {pid}")

if __name__ == "__main__":
    import uvicorn
    import os
    
    # 根据环境变量决定是否启用uvicorn日志
    enable_logging = os.getenv("ENABLE_LOGGING", "false").lower() in ("true", "1", "yes", "on")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="critical" if not enable_logging else "info",
        access_log=enable_logging  # 禁用访问日志
    )
