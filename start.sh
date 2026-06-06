#!/usr/bin/env bash
# =============================================================================
# Virtual Office — 一键部署脚本
# 用法: ./start.sh
#       ./start.sh --stop      停止服务
#       ./start.sh --restart   重启服务
#       ./start.sh --update    拉取最新镜像后重启
#       ./start.sh --logs      查看日志
#       ./start.sh --status    查看状态
# =============================================================================

set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 配置 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# ── 帮助信息 ──────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
${CYAN}My Virtual Office — 一键部署${NC}

用法: $(basename "$0") [选项]

选项:
  (无)          启动服务（默认行为）
  --stop        停止服务
  --restart     重启服务
  --update      拉取最新镜像并重启
  --logs        查看服务日志
  --status      查看服务状态
  --clean       停止服务并删除数据卷（⚠️ 会丢失所有数据）
  --help        显示此帮助信息

${CYAN}启动后访问: http://localhost:8090/setup${NC}
EOF
    exit 0
}

# ── 前置检查 ──────────────────────────────────────────────────────────────
check_prerequisites() {
    echo -e "${CYAN}[1/5] 检查运行环境...${NC}"

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        echo -e "${RED}✗ Docker 未安装${NC}"
        echo "请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Docker $(docker --version | awk '{print $3}' | tr -d ',')"

    # 检查 Docker Compose
    if ! docker compose version &>/dev/null 2>&1; then
        echo -e "${RED}✗ Docker Compose 不可用${NC}"
        echo "请确保 Docker Desktop 已安装，或单独安装 docker-compose-plugin"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Docker Compose 可用"

    # 检查 docker-compose.yml
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo -e "${RED}✗ 找不到 docker-compose.yml${NC}"
        echo "请确保在 Virtual Office 项目目录中运行此脚本"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} docker-compose.yml 存在"
}

# ── 环境配置 ──────────────────────────────────────────────────────────────
setup_env() {
    echo -e "${CYAN}[2/5] 配置环境...${NC}"

    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            echo -e "  ${GREEN}✓${NC} 已从 .env.example 创建 .env"
            echo -e "  ${YELLOW}提示: 可以编辑 .env 文件自定义配置（可选）${NC}"
        else
            echo -e "  ${YELLOW}⚠ 找不到 .env.example，使用默认配置${NC}"
            cat > "$ENV_FILE" <<EOF
# Virtual Office 环境配置
VO_OPENCLAW_PATH=~/.openclaw
VO_GATEWAY_URL=ws://host.docker.internal:18789
VO_GATEWAY_HTTP=http://host.docker.internal:18789
VO_PORT=8090
VO_WS_PORT=8091
VO_OFFICE_NAME=Virtual Office
VO_WEATHER_LOCATION=
EOF
            echo -e "  ${GREEN}✓${NC} 已创建默认 .env"
        fi
    else
        echo -e "  ${GREEN}✓${NC} .env 已存在"
    fi

    # 检查 OpenClaw 路径是否存在
    VO_PATH=$(grep '^VO_OPENCLAW_PATH=' "$ENV_FILE" | cut -d'=' -f2- | sed 's/^~/'"$HOME"'/')
    VO_PATH="${VO_PATH/#\~/$HOME}"
    if [ ! -d "$VO_PATH" ]; then
        echo -e "  ${YELLOW}⚠ OpenClaw 路径不存在: $VO_PATH${NC}"
        echo -e "  ${YELLOW}  如果没有安装 OpenClaw，仍可以 Demo 模式运行（最多 3 个代理）${NC}"
    else
        echo -e "  ${GREEN}✓${NC} OpenClaw 路径: $VO_PATH"
    fi
}

# ── 启动服务 ──────────────────────────────────────────────────────────────
start_service() {
    echo -e "${CYAN}[3/5] 拉取最新镜像...${NC}"
    cd "$SCRIPT_DIR"
    docker compose pull virtual-office 2>&1 | grep -v "^$" || true

    echo -e "${CYAN}[4/5] 启动服务...${NC}"
    docker compose up -d virtual-office

    echo -e "${CYAN}[5/5] 等待服务就绪...${NC}"
    local max_wait=30
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -sf "http://localhost:$(grep '^VO_PORT=' "$ENV_FILE" | cut -d'=' -f2-)health" &>/dev/null; then
            echo -e "  ${GREEN}✓${NC} 服务已就绪!"
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if [ $waited -ge $max_wait ]; then
        echo -e "  ${YELLOW}⚠ 服务启动超时（仍在启动中），请稍候几秒再试${NC}"
    fi
}

# ── 显示访问信息 ──────────────────────────────────────────────────────────
show_access_info() {
    local vo_port
    vo_port=$(grep '^VO_PORT=' "$ENV_FILE" | cut -d'=' -f2-)
    local vo_ws_port
    vo_ws_port=$(grep '^VO_WS_PORT=' "$ENV_FILE" | cut -d'=' -f2-)

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          My Virtual Office 已启动! 🎉           ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}"
    echo -e "${GREEN}║  🌐 办公室:    http://localhost:${vo_port}           ${NC}"
    echo -e "${GREEN}║  🧙 设置向导:  http://localhost:${vo_port}/setup     ${NC}"
    echo -e "${GREEN}║  ⚙️  模型设置:   http://localhost:${vo_port}/models.html${NC}"
    echo -e "${GREEN}║  ⏰ 定时任务:  http://localhost:${vo_port}/cron.html   ${NC}"
    echo -e "${GREEN}║${NC}"
    echo -e "${GREEN}║  📋 常用命令:                               ${NC}"
    echo -e "${GREEN}║    $(basename "$0") --status    查看服务状态          ${NC}"
    echo -e "${GREEN}║    $(basename "$0") --logs      查看服务日志          ${NC}"
    echo -e "${GREEN}║    $(basename "$0") --stop      停止服务              ${NC}"
    echo -e "${GREEN}║    $(basename "$0") --restart   重启服务              ${NC}"
    echo -e "${GREEN}║    $(basename "$0") --update    更新到最新版          ${NC}"
    echo -e "${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}💡 提示: 首次访问请打开设置向导完成配置${NC}"
    echo ""
}

# ── 停止服务 ──────────────────────────────────────────────────────────────
stop_service() {
    echo -e "${YELLOW}停止 Virtual Office 服务...${NC}"
    cd "$SCRIPT_DIR"
    docker compose down
    echo -e "${GREEN}✓ 服务已停止${NC}"
}

# ── 更新服务 ──────────────────────────────────────────────────────────────
update_service() {
    echo -e "${YELLOW}拉取最新镜像并重启...${NC}"
    cd "$SCRIPT_DIR"
    docker compose pull virtual-office
    docker compose up -d --force-recreate virtual-office
    echo -e "${GREEN}✓ 已更新并重启${NC}"
    show_access_info
}

# ── 查看日志 ──────────────────────────────────────────────────────────────
show_logs() {
    cd "$SCRIPT_DIR"
    docker compose logs -f virtual-office
}

# ── 查看状态 ──────────────────────────────────────────────────────────────
show_status() {
    cd "$SCRIPT_DIR"

    echo -e "${CYAN}服务状态:${NC}"
    docker compose ps virtual-office 2>/dev/null || echo -e "${RED}服务未运行${NC}"

    echo ""
    local vo_port
    vo_port=$(grep '^VO_PORT=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- || echo "8090")

    if curl -sf "http://localhost:${vo_port}/health" &>/dev/null; then
        echo -e "  ${GREEN}● 健康检查通过${NC}"
    else
        echo -e "  ${RED}● 服务未响应${NC}"
    fi

    # 显示容器资源使用
    if docker ps --filter name=virtual-office --format '{{.Status}}' | grep -q Up; then
        echo ""
        echo -e "${CYAN}资源使用:${NC}"
        docker stats virtual-office --no-stream --format "  CPU: {{.CPUPerc}} | 内存: {{.MemUsage}}" 2>/dev/null || true
    fi
}

# ── 清理数据 ──────────────────────────────────────────────────────────────
clean_data() {
    echo -e "${RED}⚠️  警告: 此操作将停止服务并删除所有数据卷（包括办公室布局、配置等）${NC}"
    echo -n "确认继续? [y/N] "
    read -r confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        cd "$SCRIPT_DIR"
        docker compose down -v
        echo -e "${GREEN}✓ 服务已停止，数据已清理${NC}"
    else
        echo "已取消"
    fi
}

# ── 主逻辑 ────────────────────────────────────────────────────────────────
main() {
    case "${1:-}" in
        --help|-h)   usage ;;
        --stop)      stop_service ;;
        --restart)   stop_service && start_service && show_access_info ;;
        --update)    update_service ;;
        --logs)      show_logs ;;
        --status)    show_status ;;
        --clean)     clean_data ;;
        "")
            echo -e "${CYAN}"
            echo "╔══════════════════════════════════════════╗"
            echo "║   My Virtual Office 一键部署 🏢          ║"
            echo "╚══════════════════════════════════════════╝"
            echo -e "${NC}"
            check_prerequisites
            setup_env
            start_service
            show_access_info
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            usage
            ;;
    esac
}

main "$@"
