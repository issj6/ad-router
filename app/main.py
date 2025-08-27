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
    try:
        from .db import get_session
        from sqlalchemy import text
        async with await get_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        warning(f"Database connectivity check failed: {e}")
        db_ok = False
    return HealthResponse(
        ok=db_ok,  # 整体健康状态取决于数据库连接
        timestamp=int(time.time()),
        version="1.0.0",
        db_ok=db_ok
    )

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    info("OCPX Relay System starting up...")
    
    # 这里可以添加启动时的初始化逻辑
    # 比如：预热数据库连接、加载配置等
    
    info("OCPX Relay System started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    info("OCPX Relay System shutting down...")
    
    # 清理资源
    from .services.connector import cleanup_client
    await cleanup_client()
    
    info("OCPX Relay System shutdown complete")

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
