#!/usr/bin/env python3
"""
OCPX中转系统启动脚本
"""

import os
import sys
import subprocess
import argparse

def check_dependencies():
    """检查依赖是否已安装"""
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        import httpx
        import yaml
        print("✅ 所有依赖已安装")
        return True
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return False

def check_config():
    """检查配置文件"""
    if not os.path.exists("config_example.yaml"):
        print("❌ 配置文件 config_example.yaml 不存在")
        return False
    
    try:
        import yaml
        with open("config_example.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 检查必要配置
        settings = config.get("settings", {})
        if settings.get("app_secret") == "CHANGE_ME_TO_RANDOM_SECRET":
            print("⚠️  警告: 请修改 config_example.yaml 中的 app_secret 为随机密钥")
        
        print("✅ 配置文件检查通过")
        return True
    except Exception as e:
        print(f"❌ 配置文件格式错误: {e}")
        return False

def create_data_dir():
    """创建数据目录"""
    data_dir = "./data/sqlite"
    os.makedirs(data_dir, exist_ok=True)
    print(f"✅ 数据目录已创建: {data_dir}")

def main():
    parser = argparse.ArgumentParser(description="OCPX中转系统启动脚本")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=6789, help="监听端口")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    parser.add_argument("--reload", action="store_true", help="开启热重载（开发模式）")
    parser.add_argument("--production", action="store_true", help="生产模式（使用gunicorn）")
    
    args = parser.parse_args()
    
    print("🚀 OCPX中转系统启动检查...")
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 检查配置
    if not check_config():
        sys.exit(1)
    
    # 创建数据目录
    create_data_dir()
    
    print("\n🎯 启动服务...")
    
    if args.production:
        # 生产模式使用gunicorn
        try:
            import gunicorn
        except ImportError:
            print("❌ 生产模式需要安装 gunicorn: pip install gunicorn")
            sys.exit(1)
        
        cmd = [
            "gunicorn",
            "app.main:app",
            f"-w", str(args.workers),
            "-k", "uvicorn.workers.UvicornWorker",
            "--bind", f"{args.host}:{args.port}",
            "--access-logfile", "-",
            "--error-logfile", "-"
        ]
        print(f"执行命令: {' '.join(cmd)}")
        subprocess.run(cmd)
    else:
        # 开发模式使用uvicorn
        cmd = [
            "python", "-m", "uvicorn",
            "app.main:app",
            "--host", args.host,
            "--port", str(args.port)
        ]
        
        if args.reload:
            cmd.append("--reload")
        
        print(f"执行命令: {' '.join(cmd)}")
        print(f"服务地址: http://{args.host}:{args.port}")
        print(f"API文档: http://{args.host}:{args.port}/docs")
        print("按 Ctrl+C 停止服务\n")
        
        subprocess.run(cmd)

if __name__ == "__main__":
    main()
