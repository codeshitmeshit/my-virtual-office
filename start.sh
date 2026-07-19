#!/usr/bin/env bash
# =============================================================================
# Virtual Office — 一键启动脚本
# 用法: ./start.sh              本地启动
#       ./start.sh --browser    启动可选 Agent Browser 镜像
#       ./start.sh --help       显示帮助
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
BROWSER_COMPOSE_FILE="$SCRIPT_DIR/docker-compose.browser.yml"
source "$SCRIPT_DIR/scripts/hr-env-defaults.sh"

# ── 帮助信息 ──────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
${CYAN}My Virtual Office — 本地启动${NC}

用法: $(basename "$0") [选项]

选项:
  (无)               直接运行本地 Python 服务（不使用 Docker）
  --browser          构建并启动可选 Agent Browser 镜像
  --browser-stop     停止 Agent Browser
  --browser-restart  重启 Agent Browser
  --browser-logs     查看 Agent Browser 日志
  --browser-status   查看 Agent Browser 状态
  --help             显示此帮助信息

${CYAN}本地启动后访问: http://localhost:8090/setup${NC}
${CYAN}Agent Browser: CDP http://127.0.0.1:9224，Viewer https://localhost:6901${NC}
EOF
    exit 0
}

is_truthy() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON|enabled|ENABLED) return 0 ;;
        *) return 1 ;;
    esac
}

warn_if_browser_unavailable() {
    local browser_enabled="${VO_BROWSER_PANEL:-}"
    local cdp_url="${VO_CDP_URL:-}"
    if ! is_truthy "$browser_enabled"; then
        return 0
    fi
    if [ -z "$cdp_url" ]; then
        echo -e "  ${YELLOW}⚠ 已启用代理浏览器面板，但未配置 VO_CDP_URL${NC}"
        echo -e "  ${YELLOW}  可运行 ./start.sh --browser，或在 .env 中配置其他 Chrome DevTools 地址${NC}"
        return 0
    fi

    local check_url
    check_url="${cdp_url/localhost/127.0.0.1}"
    check_url="${check_url%/}"
    if curl -sf "${check_url}/json/version" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 代理浏览器 CDP 可用: ${check_url}"
        return 0
    fi

    echo -e "  ${YELLOW}⚠ 代理浏览器面板已启用，但 CDP 不可达: ${cdp_url}${NC}"
    echo -e "  ${YELLOW}  可运行 ./start.sh --browser，或确认已配置的 Chrome 调试端口可达${NC}"
}

# ── 环境配置 ──────────────────────────────────────────────────────────────
setup_env() {
    echo -e "${CYAN}[配置] 检查环境文件...${NC}"

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
# VO_GATEWAY_URL=ws://127.0.0.1:18790
# VO_GATEWAY_HTTP=http://127.0.0.1:18790
VO_PORT=8090
VO_WS_PORT=8091
VO_OFFICE_NAME=Virtual Office
VO_WEATHER_LOCATION=
VO_BROWSER_PANEL=true
VO_CDP_URL=http://127.0.0.1:9224
VO_VIEWER_URL=https://localhost:6901
VO_PC_METRICS_ENABLED=true
VO_PC_METRICS_URL=http://127.0.0.1:8099
VO_API_USAGE=false
VO_AGENT_PROJECT_AUTHORING_ENABLED=true
EOF
            echo -e "  ${GREEN}✓${NC} 已创建默认 .env"
        fi
    else
        echo -e "  ${GREEN}✓${NC} .env 已存在"
    fi

    # 补齐新版本新增的可选配置，避免旧 .env 缺少启动开关。
    if ! grep -q '^VO_BROWSER_PANEL=' "$ENV_FILE"; then
        {
            echo ""
            echo "# Agent Browser panel (optional)"
            echo "VO_BROWSER_PANEL=true"
        } >> "$ENV_FILE"
        echo -e "  ${GREEN}✓${NC} 已补充浏览器面板启动配置到 .env"
    fi
    if ! grep -q '^VO_CDP_URL=' "$ENV_FILE"; then
        echo "VO_CDP_URL=http://127.0.0.1:9224" >> "$ENV_FILE"
    fi
    if ! grep -q '^VO_VIEWER_URL=' "$ENV_FILE"; then
        echo "VO_VIEWER_URL=https://localhost:6901" >> "$ENV_FILE"
    fi
    if ! grep -q '^VO_PC_METRICS_ENABLED=' "$ENV_FILE"; then
        echo "VO_PC_METRICS_ENABLED=true" >> "$ENV_FILE"
    fi
    if ! grep -q '^VO_PC_METRICS_URL=' "$ENV_FILE"; then
        echo "VO_PC_METRICS_URL=http://127.0.0.1:8099" >> "$ENV_FILE"
    fi
    if ! grep -q '^VO_API_USAGE=' "$ENV_FILE"; then
        echo "VO_API_USAGE=false" >> "$ENV_FILE"
    fi
    if ! grep -q '^VO_AGENT_PROJECT_AUTHORING_ENABLED=' "$ENV_FILE"; then
        {
            echo ""
            echo "# Agent-managed VO project authoring"
            echo "VO_AGENT_PROJECT_AUTHORING_ENABLED=true"
        } >> "$ENV_FILE"
        echo -e "  ${GREEN}✓${NC} 已补充 Agent 项目创作开关到 .env"
    fi
    ensure_hr_env_defaults "$ENV_FILE"

    # 检查 OpenClaw 路径是否存在
    VO_PATH=$(grep '^VO_OPENCLAW_PATH=' "$ENV_FILE" | cut -d'=' -f2- | sed "s#^~#$HOME#")
    VO_PATH="${VO_PATH/#\~/$HOME}"
    if [ ! -d "$VO_PATH" ]; then
        echo -e "  ${YELLOW}⚠ OpenClaw 路径不存在: $VO_PATH${NC}"
        echo -e "  ${YELLOW}  如果没有安装 OpenClaw，仍可以 Demo 模式运行（最多 3 个代理）${NC}"
    else
        echo -e "  ${GREEN}✓${NC} OpenClaw 路径: $VO_PATH"
    fi
}

# ── 可选 Agent Browser 镜像 ──────────────────────────────────────────────
check_browser_prerequisites() {
    if ! command -v docker &>/dev/null; then
        echo -e "${RED}✗ Docker 未安装${NC}"
        echo "Docker 只用于可选 Agent Browser；主应用仍由 ./start.sh 在宿主机运行。"
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo -e "${RED}✗ Docker Compose 插件不可用${NC}"
        exit 1
    fi
    if [ ! -f "$BROWSER_COMPOSE_FILE" ]; then
        echo -e "${RED}✗ 找不到浏览器配置: $BROWSER_COMPOSE_FILE${NC}"
        exit 1
    fi
}

browser_compose() {
    docker compose --project-directory "$SCRIPT_DIR" -f "$BROWSER_COMPOSE_FILE" "$@"
}

show_browser_access_info() {
    echo -e "${GREEN}✓ Agent Browser 已启动${NC}"
    echo "  CDP:    http://127.0.0.1:9224"
    echo "  Viewer: https://localhost:6901"
}

start_browser_service() {
    check_browser_prerequisites
    setup_env
    echo -e "${CYAN}构建并启动可选 Agent Browser...${NC}"
    browser_compose build agent-browser
    browser_compose up -d --force-recreate agent-browser

    for _ in $(seq 1 60); do
        if curl -sf http://127.0.0.1:9224/json/version >/dev/null 2>&1; then
            show_browser_access_info
            return 0
        fi
        sleep 1
    done

    echo -e "${YELLOW}⚠ Agent Browser 已启动，但 CDP 尚未就绪${NC}"
    echo "  使用 ./start.sh --browser-logs 查看日志"
}

stop_browser_service() {
    check_browser_prerequisites
    browser_compose down
}

restart_browser_service() {
    check_browser_prerequisites
    browser_compose restart agent-browser
    show_browser_access_info
}

show_browser_logs() {
    check_browser_prerequisites
    browser_compose logs -f agent-browser
}

show_browser_status() {
    check_browser_prerequisites
    browser_compose ps agent-browser
}

# ── 本地启动 ──────────────────────────────────────────────────────────────
start_local() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════╗"
    echo "║   My Virtual Office 本地启动 🏢          ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"

    echo -e "${CYAN}[1/3] 检查运行环境...${NC}"

    # 检查 Python3
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}✗ Python3 未安装${NC}"
        echo "请先安装 Python 3.10+"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Python $(python3 --version 2>&1)"

    local python_bin="python3"
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        python_bin="$SCRIPT_DIR/.venv/bin/python"
    fi

    # 检查 websockets 库。server.py 需要 websockets.asyncio.client；
    # 仅能 import websockets 的旧版本会在启动时失败。
    if ! "$python_bin" -c "from websockets.asyncio.client import connect" 2>/dev/null; then
        echo -e "  ${YELLOW}⚠ websockets 版本过旧或未安装，正在安装...${NC}"
        if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
            python3 -m venv "$SCRIPT_DIR/.venv" || {
                echo -e "${RED}✗ 创建 Python 虚拟环境失败${NC}"
                echo "请安装 python3-venv，或手动创建 .venv 后安装: python -m pip install 'websockets>=13'"
                exit 1
            }
        fi
        python_bin="$SCRIPT_DIR/.venv/bin/python"
        "$python_bin" -m pip install 'websockets>=13' 2>&1 | tail -1
        if ! "$python_bin" -c "from websockets.asyncio.client import connect" 2>/dev/null; then
            echo -e "${RED}✗ websockets 安装失败${NC}"
            echo "请手动运行: $python_bin -m pip install 'websockets>=13'"
            exit 1
        fi
    fi
    echo -e "  ${GREEN}✓${NC} websockets 可用"

    if ! "$python_bin" -c "import lark_oapi" 2>/dev/null; then
        echo -e "  ${YELLOW}⚠ lark-oapi 未安装，正在安装飞书长连接 SDK...${NC}"
        if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
            python3 -m venv "$SCRIPT_DIR/.venv" || {
                echo -e "${RED}✗ 创建 Python 虚拟环境失败${NC}"
                echo "请安装 python3-venv，或手动创建 .venv 后安装: python -m pip install 'lark-oapi>=1.7,<2'"
                exit 1
            }
        fi
        python_bin="$SCRIPT_DIR/.venv/bin/python"
        "$python_bin" -m pip install 'lark-oapi>=1.7,<2' 2>&1 | tail -1
        if ! "$python_bin" -c "import lark_oapi" 2>/dev/null; then
            echo -e "${RED}✗ lark-oapi 安装失败${NC}"
            echo "请手动运行: $python_bin -m pip install 'lark-oapi>=1.7,<2'"
            exit 1
        fi
    fi
    echo -e "  ${GREEN}✓${NC} lark-oapi 可用"

    # The Feishu Agent Chat channel uses an isolated Node worker. Dependency
    # failures are Chat-only: keep VO and the notification app startable and
    # expose the actionable failure through the Chat status surface.
    local feishu_worker_dir="$SCRIPT_DIR/integrations/feishu-channel-worker"
    if ! command -v node &>/dev/null; then
        echo -e "  ${YELLOW}⚠ Node.js 18+ 未安装；飞书 Agent 对话通道将报告 missing_node_runtime${NC}"
    elif [ "$(node -p 'Number(process.versions.node.split(".")[0]) >= 18' 2>/dev/null)" != "true" ]; then
        echo -e "  ${YELLOW}⚠ Node.js 版本低于 18；飞书 Agent 对话通道将报告 incompatible_node_runtime${NC}"
    elif ! (cd "$feishu_worker_dir" && node src/preflight.mjs >/dev/null 2>&1); then
        echo -e "  ${YELLOW}⚠ 正在安装飞书 Agent 对话通道锁定依赖...${NC}"
        if (cd "$feishu_worker_dir" && npm ci --omit=dev --ignore-scripts --no-audit --no-fund); then
            echo -e "  ${GREEN}✓${NC} @larksuite/channel 锁定依赖已安装"
        else
            echo -e "  ${YELLOW}⚠ 飞书 Agent 对话依赖安装失败；VO 将继续启动，Chat 状态会提供修复命令${NC}"
        fi
    else
        echo -e "  ${GREEN}✓${NC} 飞书 Agent 对话 Node Worker 依赖可用"
    fi

    setup_env

    echo -e "${CYAN}[2/3] 准备数据目录...${NC}"
    local data_dir
    data_dir=$(grep '^VO_OPENCLAW_PATH=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | sed "s#^~#$HOME#" || echo "$HOME/.openclaw")
    data_dir="${data_dir/#\~/$HOME}"
    local status_dir="$SCRIPT_DIR/data"
    mkdir -p "$status_dir"
    echo -e "  ${GREEN}✓${NC} 数据目录: $status_dir"

    echo -e "${CYAN}[3/3] 启动服务...${NC}"

    # 加载环境变量（.env 优先，未设置则使用默认值）
    set -a
    source "$ENV_FILE" 2>/dev/null || true
    set +a

    export VO_STATUS_DIR="${VO_STATUS_DIR:-$status_dir}"
    VO_STATUS_DIR=$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$VO_STATUS_DIR")
    export VO_STATUS_DIR
    mkdir -p "$VO_STATUS_DIR"
    export VO_OPENCLAW_PATH="${VO_OPENCLAW_PATH:-$data_dir}"
    export VO_PORT="${VO_PORT:-8090}"
    export VO_WS_PORT="${VO_WS_PORT:-8091}"
    export VO_MANAGEMENT_TOKEN="${VO_MANAGEMENT_TOKEN:-4285}"
    export VO_WS_PATH="${VO_WS_PATH:-/ws}"
    export VO_OFFICE_NAME="${VO_OFFICE_NAME:-Virtual Office}"
    export _VO_INT=1
    local gateway_port
    gateway_port=$(python3 - "$VO_OPENCLAW_PATH" <<'PY' 2>/dev/null || true
import json
import os
import sys

cfg_path = os.path.join(os.path.expanduser(sys.argv[1]), "openclaw.json")
try:
    with open(cfg_path, "r") as f:
        cfg = json.load(f)
    port = (cfg.get("gateway") or {}).get("port")
    if port:
        print(port)
except (OSError, json.JSONDecodeError, TypeError):
    pass
PY
)
    gateway_port="${gateway_port:-18789}"
    export VO_GATEWAY_URL="${VO_GATEWAY_URL:-ws://localhost:${gateway_port}}"
    export VO_GATEWAY_HTTP="${VO_GATEWAY_HTTP:-http://localhost:${gateway_port}}"
    export VO_BROWSER_PANEL="${VO_BROWSER_PANEL:-true}"
    export VO_CDP_URL="${VO_CDP_URL:-http://127.0.0.1:9224}"
    export VO_VIEWER_URL="${VO_VIEWER_URL:-https://localhost:6901}"
    export VO_PC_METRICS_ENABLED="${VO_PC_METRICS_ENABLED:-true}"
    export VO_PC_METRICS_URL="${VO_PC_METRICS_URL:-http://127.0.0.1:8099}"
    export VO_API_USAGE="${VO_API_USAGE:-false}"
    export VO_AGENT_PROJECT_AUTHORING_ENABLED="${VO_AGENT_PROJECT_AUTHORING_ENABLED:-true}"
    export VO_HR_ENABLED="${VO_HR_ENABLED:-true}"
    export VO_HR_SCHEDULER_ENABLED="${VO_HR_SCHEDULER_ENABLED:-false}"
    export VO_HR_TIMEZONE="${VO_HR_TIMEZONE:-${VO_TIMEZONE:-${TZ:-UTC}}}"
    export VO_HR_DAILY_TIME="${VO_HR_DAILY_TIME:-18:00}"
    export VO_HR_SUBMISSION_WINDOW_MINUTES="${VO_HR_SUBMISSION_WINDOW_MINUTES:-120}"
    export VO_HR_MAX_WORKERS="${VO_HR_MAX_WORKERS:-2}"
    export VO_HR_AGENT_TIMEOUT_SECONDS="${VO_HR_AGENT_TIMEOUT_SECONDS:-30}"
    export VO_HR_RETRY_LIMIT="${VO_HR_RETRY_LIMIT:-3}"
    export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
    export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

    for port_name in VO_PORT VO_WS_PORT; do
        local port="${!port_name}"
        if "$python_bin" - "$port" <<'PY'
import socket
import sys

try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.5):
        pass
except OSError:
    raise SystemExit(1)
PY
        then
            echo -e "${RED}✗ ${port_name}=${port} 已被占用，请先停止旧服务${NC}"
            exit 1
        fi
    done

    echo -e "  ${GREEN}✓${NC} 环境已配置"
    echo -e "  ${GREEN}✓${NC} 状态目录: $VO_STATUS_DIR"
    echo -e "  ${GREEN}✓${NC} HTTP/WS 端口可用: ${VO_PORT}/${VO_WS_PORT}"
    echo ""

    # Cache-busting
    local cache_v
    cache_v=$(date +%s)
    sed -i "s/?v=[0-9]*/?v=${cache_v}/g" "$SCRIPT_DIR/app/index.html" 2>/dev/null || true

    cd "$SCRIPT_DIR/app"
    "$python_bin" server.py &
    local server_pid=$!
    trap 'kill "${server_pid:-}" 2>/dev/null || true' INT TERM EXIT

    local ready=false
    for _ in $(seq 1 60); do
        if ! kill -0 "$server_pid" 2>/dev/null; then
            echo -e "${RED}✗ 服务进程提前退出${NC}"
            wait "$server_pid"
            exit $?
        fi
        if "$python_bin" - "$VO_PORT" <<'PY' 2>/dev/null
import http.client
import sys

conn = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=1)
conn.request("GET", "/health")
response = conn.getresponse()
raise SystemExit(0 if response.status == 200 else 1)
PY
        then
            ready=true
            break
        fi
        sleep 0.5
    done

    if [ "$ready" != true ]; then
        echo -e "${RED}✗ HTTP 健康检查超时，服务未就绪${NC}"
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
        exit 1
    fi

    if ! "$python_bin" - "$VO_WS_PORT" <<'PY'
import asyncio
import sys
from websockets.asyncio.client import connect

async def check():
    async with connect(f"ws://127.0.0.1:{sys.argv[1]}", open_timeout=2):
        pass

asyncio.run(check())
PY
    then
        echo -e "${RED}✗ WebSocket 端口 ${VO_WS_PORT} 未监听${NC}"
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
        exit 1
    fi

    "$python_bin" - "$VO_PORT" "$VO_STATUS_DIR/startup-health.json" "$VO_VIEWER_URL" <<'PY'
import asyncio
import http.client
import json
import ssl
import sys
import time
import urllib.parse
from websockets.asyncio.client import connect

port, output, viewer_url = sys.argv[1:]
base = f"http://127.0.0.1:{port}"
report = {"checkedAt": int(time.time()), "http": True, "websocket": True}
for name, path in (
    ("gateway", "/api/gateway/test"),
    ("browser", "/browser-status"),
    ("license", "/api/license"),
):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=3)
        conn.request("GET", path)
        response = conn.getresponse()
        report[name] = json.loads(response.read().decode("utf-8"))
        conn.close()
    except Exception as exc:
        report[name] = {"ok": False, "error": str(exc)}

async def check_viewer_websocket():
    parsed = urllib.parse.urlsplit(viewer_url)
    query = urllib.parse.parse_qs(parsed.query)
    path = query.get("path", [None])[0]
    if not path:
        base_path = parsed.path.strip("/")
        path = f"{base_path}/websockify" if base_path else "websockify"
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = urllib.parse.urlunsplit((ws_scheme, parsed.netloc, "/" + path.lstrip("/"), "", ""))
    ssl_context = None
    if ws_scheme == "wss":
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    async with connect(
        ws_url,
        ssl=ssl_context,
        subprotocols=["binary"],
        origin=f"{parsed.scheme}://{parsed.netloc}",
        open_timeout=5,
    ):
        return ws_url

try:
    viewer_ws_url = asyncio.run(check_viewer_websocket())
    report["viewerWebsocket"] = {"ok": True, "url": viewer_ws_url}
except Exception as exc:
    report["viewerWebsocket"] = {"ok": False, "error": str(exc)}

with open(output, "w") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, ensure_ascii=False))
PY

    warn_if_browser_unavailable

    echo ""
    echo -e "${GREEN}✓ HTTP 已就绪: http://localhost:${VO_PORT}${NC}"
    echo -e "${GREEN}✓ WebSocket 已监听: 127.0.0.1:${VO_WS_PORT}${NC}"
    echo -e "  启动报告: $VO_STATUS_DIR/startup-health.json"
    echo -e "  按 Ctrl+C 停止服务"
    echo ""

    wait "$server_pid"
    local exit_code=$?
    trap - INT TERM EXIT
    exit "$exit_code"
}

# ── 主逻辑 ────────────────────────────────────────────────────────────────
main() {
    case "${1:-}" in
        --help|-h) usage ;;
        --browser) start_browser_service ;;
        --browser-stop) stop_browser_service ;;
        --browser-restart) restart_browser_service ;;
        --browser-logs) show_browser_logs ;;
        --browser-status) show_browser_status ;;
        "") start_local ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            usage
            ;;
    esac
}

main "$@"
