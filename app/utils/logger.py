"""
统一的异步日志配置模块
使用 Loguru 替换标准库 logging，启用异步模式提升性能
支持环境变量开关控制，默认完全关闭日志以获得最佳性能
"""

import sys
import os
from loguru import logger
from pathlib import Path

# 日志开关配置 - 默认关闭
ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "false").lower() in ("true", "1", "yes", "on")

def setup_logger():
    """配置 Loguru 异步日志系统 - 支持开关控制"""
    
    # 移除默认的控制台处理器
    logger.remove()
    
    # 禁用第三方库的日志
    _disable_third_party_logs()
    
    # 如果日志被禁用，则不添加任何处理器
    if not ENABLE_LOGGING:
        return
    
    # 获取日志级别（默认 INFO）
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # 控制台输出配置 - 异步队列
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
        enqueue=True,  # 启用异步队列
        backtrace=True,
        diagnose=True
    )
    
    # 文件输出配置 - 异步队列 + 轮转
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 应用主日志文件
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",  # 每天轮转
        retention="7 days",  # 保留7天
        compression="gz",  # 压缩旧日志
        enqueue=True,  # 启用异步队列
        backtrace=True,
        diagnose=True
    )
    
    # 错误专用日志文件 - 只记录 ERROR 及以上
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
        rotation="1 day",
        retention="30 days",  # 错误日志保留更久
        compression="gz",
        enqueue=True,  # 启用异步队列
        backtrace=True,
        diagnose=True
    )
    
    # 性能关键路径的专用日志（可选，用于调试）
    if log_level == "DEBUG":
        logger.add(
            log_dir / "performance_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
            rotation="1 day",
            retention="3 days",
            compression="gz",
            enqueue=True,
            filter=lambda record: record["extra"].get("performance", False)
        )

def _disable_third_party_logs():
    """禁用第三方库的日志输出"""
    import logging as std_logging
    
    # 禁用或降低第三方库日志级别
    libraries_to_silence = [
        "fastapi",
        "uvicorn", 
        "uvicorn.access",
        "uvicorn.error", 
        "starlette",
        "httpx",
        "httpcore",
        "asyncio",
        "sqlalchemy",
        "asyncmy"
    ]
    
    for lib in libraries_to_silence:
        std_logging.getLogger(lib).setLevel(std_logging.CRITICAL)
        std_logging.getLogger(lib).propagate = False

def get_logger(name: str = None):
    """获取配置好的 logger 实例"""
    if name:
        return logger.bind(name=name)
    return logger

# 初始化日志配置
setup_logger()

# 导出常用的日志方法，支持开关控制
if ENABLE_LOGGING:
    # 启用日志时使用真实的 loguru 实现
    def info(message: str, **kwargs):
        """异步 INFO 级别日志"""
        logger.info(message, **kwargs)

    def debug(message: str, **kwargs):
        """异步 DEBUG 级别日志"""
        logger.debug(message, **kwargs)

    def warning(message: str, **kwargs):
        """异步 WARNING 级别日志"""
        logger.warning(message, **kwargs)

    def error(message: str, **kwargs):
        """异步 ERROR 级别日志"""
        logger.error(message, **kwargs)

    def critical(message: str, **kwargs):
        """异步 CRITICAL 级别日志"""
        logger.critical(message, **kwargs)

    def perf_info(message: str, **kwargs):
        """性能关键路径日志 - 带特殊标记"""
        logger.bind(performance=True).info(message, **kwargs)
        
else:
    # 禁用日志时使用空操作实现，获得最佳性能
    def info(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

    def debug(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

    def warning(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

    def error(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

    def critical(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

    def perf_info(message: str, **kwargs):
        """空操作 - 日志已禁用"""
        pass

# 兼容标准 logging 的对象接口 - 支持开关控制
if ENABLE_LOGGING:
    class LoguruAdapter:
        """Loguru 适配器，提供与标准 logging 相似的接口"""
        
        @staticmethod
        def info(msg, *args, **kwargs):
            if args:
                msg = msg % args
            logger.info(msg)
        
        @staticmethod
        def debug(msg, *args, **kwargs):
            if args:
                msg = msg % args
            logger.debug(msg)
        
        @staticmethod
        def warning(msg, *args, **kwargs):
            if args:
                msg = msg % args
            logger.warning(msg)
        
        @staticmethod
        def error(msg, *args, **kwargs):
            if args:
                msg = msg % args
            logger.error(msg)
        
        @staticmethod
        def critical(msg, *args, **kwargs):
            if args:
                msg = msg % args
            logger.critical(msg)
else:
    class LoguruAdapter:
        """空操作适配器 - 日志已禁用"""
        
        @staticmethod
        def info(msg, *args, **kwargs):
            pass
        
        @staticmethod
        def debug(msg, *args, **kwargs):
            pass
        
        @staticmethod
        def warning(msg, *args, **kwargs):
            pass
        
        @staticmethod
        def error(msg, *args, **kwargs):
            pass
        
        @staticmethod
        def critical(msg, *args, **kwargs):
            pass

# 创建一个全局的适配器实例，方便替换
logging = LoguruAdapter()
