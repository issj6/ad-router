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
    config_dir = os.getenv("CONFIG_DIR", "./config")
    main_config_file = os.path.join(config_dir, "main.yaml")
    
    # 检查是否有远程配置URL
    main_config_url = os.getenv("MAIN_CONFIG_URL")
    if main_config_url:
        print(f"✅ 使用远程主配置: {main_config_url}")
        return True
    
    # 检查本地配置目录
    if not os.path.exists(config_dir):
        print(f"❌ 配置目录不存在: {config_dir}")
        print("💡 解决方案:")
        print("   1. 设置环境变量 CONFIG_DIR 指向配置目录")
        print("   2. 或创建默认配置目录 ./config")
        print("   3. 或设置环境变量 MAIN_CONFIG_URL 指向远程配置")
        return False
    
    if not os.path.exists(main_config_file):
        print(f"❌ 主配置文件不存在: {main_config_file}")
        print("💡 解决方案:")
        print("   1. 创建 main.yaml 文件")
        print("   2. 参考 config/README.md 了解配置格式")
        return False
    
    try:
        import yaml
        with open(main_config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 检查必要配置
        settings = config.get("settings", {})
        if not settings:
            print("⚠️  警告: 配置文件中缺少 settings 配置")
        
        upstream_configs = config.get("upstream_configs", [])
        if not upstream_configs:
            print("⚠️  警告: 没有配置任何上游")
        
        print("✅ 配置文件检查通过")
        print(f"   配置目录: {config_dir}")
        print(f"   上游数量: {len(upstream_configs)}")
        return True
    except Exception as e:
        print(f"❌ 配置文件格式错误: {e}")
        return False

def create_data_dir():
    """创建数据目录（MySQL模式下无需操作）"""
    print("✅ 使用MySQL数据库，无需创建本地数据目录")

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
            import gunicorn  # type: ignore
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
