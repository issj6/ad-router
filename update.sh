#!/bin/bash

# 一键更新脚本
# 功能：拉取最新代码并重新部署

set -e  # 遇到错误立即退出

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/update.log"
REMOTE_URL="https://git.yylx.win/https://github.com/issj6/ad-router.git"
BRANCH="master"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")
            echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        "WARN")
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        "DEBUG")
            echo -e "${BLUE}[DEBUG]${NC} $message"
            ;;
    esac
    
    # 同时写入日志文件
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# 错误处理函数
handle_error() {
    local exit_code=$1
    local line_number=$2
    log "ERROR" "脚本在第 $line_number 行执行失败，退出码: $exit_code"
    log "ERROR" "更新失败！请检查错误信息并手动处理"
    exit $exit_code
}

# 设置错误陷阱
trap 'handle_error $? $LINENO' ERR

# 主函数
main() {
    log "INFO" "=========================================="
    log "INFO" "开始执行一键更新脚本"
    log "INFO" "=========================================="
    
    # 检查当前目录
    if [[ ! -f "deploy.sh" ]]; then
        log "ERROR" "当前目录不是项目根目录（找不到 deploy.sh）"
        log "ERROR" "请在项目根目录运行此脚本"
        exit 1
    fi
    
    # 检查网络连接
    log "INFO" "检查网络连接..."
    if ! ping -c 1 -W 3 git.yylx.win &> /dev/null; then
        log "WARN" "无法连接到 git.yylx.win，请检查网络连接"
    fi
    
    # 检查 Git 状态
    log "INFO" "检查 Git 状态..."
    if [[ -n "$(git status --porcelain)" ]]; then
        log "WARN" "工作目录有未提交的更改："
        git status --short
        read -p "是否继续更新？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "INFO" "用户取消更新"
            exit 0
        fi
    fi
    
    # 步骤1: 拉取最新代码
    log "INFO" "步骤 1/2: 拉取最新代码..."
    log "INFO" "执行: git pull $REMOTE_URL $BRANCH"
    
    if git pull "$REMOTE_URL" "$BRANCH"; then
        log "INFO" "✅ 代码拉取成功"
    else
        log "ERROR" "❌ 代码拉取失败"
        exit 1
    fi
    
    # 显示最新提交信息
    log "INFO" "最新提交信息："
    git log --oneline -3
    
    # 步骤2: 执行部署
    log "INFO" "步骤 2/2: 执行部署脚本..."
    log "INFO" "执行: ./deploy.sh"
    
    # 检查 deploy.sh 是否可执行
    if [[ ! -x "deploy.sh" ]]; then
        log "WARN" "deploy.sh 不可执行，正在添加执行权限..."
        chmod +x deploy.sh
    fi
    
    if ./deploy.sh; then
        log "INFO" "✅ 部署执行完成"
    else
        log "ERROR" "❌ 部署执行失败"
        exit 1
    fi
    
    # 完成
    log "INFO" "=========================================="
    log "INFO" "🎉 一键更新完成！"
    log "INFO" "=========================================="
    log "INFO" "日志文件: $LOG_FILE"
    
    # 显示服务状态
    if command -v docker-compose &> /dev/null; then
        log "INFO" "Docker Compose 服务状态："
        docker-compose ps
    fi
}

# 使用说明
usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -v, --verbose  详细输出模式"
    echo ""
    echo "功能:"
    echo "  1. 从远程仓库拉取最新代码"
    echo "  2. 执行部署脚本"
    echo ""
    echo "示例:"
    echo "  $0              # 执行完整更新流程"
    echo "  $0 --verbose    # 详细输出模式"
}

# 参数处理
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--verbose)
            set -x  # 开启详细输出
            shift
            ;;
        *)
            log "ERROR" "未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

# 执行主函数
main "$@"
