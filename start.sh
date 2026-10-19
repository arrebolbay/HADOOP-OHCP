#!/usr/bin/env bash
# =============================================================================
# start.sh —— 一键启动：后端 API + 前端页面（单进程）+ 自动打开浏览器
# =============================================================================
# 用法：
#   ./start.sh                     # 默认 http://127.0.0.1:8000
#   ./start.sh --port=8080         # 指定端口
#   ./start.sh --planner=rule      # 强制规则规划器（无网/无 Key 演示）
#   ./start.sh --prepare           # 强制重建分片+清洗（数据有更新时）
#   ./start.sh --no-browser        # 不自动开浏览器（录屏时可手动控制）
#
# 说明：
#   * 前端页面由 web/server.py 直接托管，后端 API 同进程，所以只需启动一个服务；
#   * 启动前会检查 Python 依赖与本地数据；缺少清洗分片时自动执行 step02/step03；
#   * Hadoop/Hive/MySQL 不是网页启动的硬依赖：Agent 会读本地清洗分片，
#     MySQL 可用时自动做跨引擎对账。
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PORT="${AQ_WEB_PORT:-8000}"
PLANNER="${AQ_PLANNER:-auto}"
OPEN_BROWSER=1
PREPARE=0

for arg in "$@"; do
  case "$arg" in
    --port=*)      PORT="${arg#*=}" ;;
    --planner=*)   PLANNER="${arg#*=}" ;;
    --prepare)     PREPARE=1 ;;
    --no-browser)  OPEN_BROWSER=0 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：$arg（用 --help 查看用法）"; exit 2 ;;
  esac
done

URL="http://127.0.0.1:${PORT}"

echo "=============================================================="
echo "  空气质量时序分析 Agent · 一键启动"
echo "  前端 + 后端：$URL"
echo "=============================================================="

# ---------- 1. Python 依赖 ----------
if ! python3 - <<'PY' >/dev/null 2>&1
import pandas, matplotlib, pymysql, requests
PY
then
  echo "[依赖] 缺少 Python 库，尝试安装 requirements.txt …"
  python3 -m pip install -q -r requirements.txt || {
    echo "[依赖] 安装失败，请手动执行：pip install -r requirements.txt"; exit 1; }
fi
echo "[依赖] Python 库检查通过"

# ---------- 2. 端口占用检查 ----------
if curl -s -m 2 "${URL}/api/health" >/dev/null 2>&1; then
  echo "[服务] 检测到服务已在运行：${URL}"
  if [ "$OPEN_BROWSER" -eq 1 ]; then
    if command -v wslview >/dev/null 2>&1; then wslview "$URL" >/dev/null 2>&1 &
    elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$URL" >/dev/null 2>&1 &
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 &
    fi
  fi
  exit 0
fi

# ---------- 3. 数据自检 / 自动准备 ----------
DAILY=$(find data/raw/daily -maxdepth 1 -name 'china_cities_*.csv' 2>/dev/null | wc -l | tr -d ' ')
CLEAN=$(find data/cache/cleaned -maxdepth 1 -name 'air_quality_*.csv' 2>/dev/null | wc -l | tr -d ' ')
echo "[数据] 原始日文件 ${DAILY} 天，清洗分片 ${CLEAN} 个"

if [ "$PREPARE" -eq 1 ] || [ "$CLEAN" -eq 0 ]; then
  if [ "$DAILY" -eq 0 ] && [ ! -d data/raw/tianchi ]; then
    echo "[数据] 未找到原始数据：请先运行"
    echo "        python3 scripts/download_real_data.py --start 2024-01-01 --end 2024-12-31"
    echo "        或把天池 CSV 放到 data/raw/tianchi/"
    exit 1
  fi
  echo "[数据] 开始生成分片与清洗（首次约 2~5 分钟）…"
  python3 steps/step02_prepare_data.py
  python3 steps/step03_explore_data.py
else
  echo "[数据] 已就绪，跳过准备（要重建请加 --prepare）"
fi

# ---------- 4. 启动服务 ----------
echo "[服务] 启动 Web 服务（规划器：$PLANNER）…"
nohup python3 web/server.py --port "$PORT" --planner "$PLANNER" \
  > logs/web.log 2>&1 &
SERVER_PID=$!
trap 'echo; echo "[服务] 正在停止…"; kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 40); do
  if curl -s -m 2 "${URL}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -s -m 2 "${URL}/api/health" >/dev/null 2>&1; then
  echo "[服务] 启动失败，请查看 logs/web.log"
  tail -20 logs/web.log || true
  exit 1
fi
echo "[服务] 已就绪：${URL}"

# ---------- 5. 打开浏览器 ----------
if [ "$OPEN_BROWSER" -eq 1 ]; then
  if command -v wslview >/dev/null 2>&1; then
    wslview "$URL" >/dev/null 2>&1 &
  elif command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$URL" >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  else
    echo "[提示] 未找到浏览器命令，请手动打开 ${URL}"
  fi
fi

echo "--------------------------------------------------------------"
echo "  演示提示：右上角「技术栈 / 说明」可用于 1.5 分钟开场"
echo "  停止服务：Ctrl+C"
echo "--------------------------------------------------------------"

wait "$SERVER_PID"
