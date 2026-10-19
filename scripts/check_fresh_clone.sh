#!/usr/bin/env bash
# =============================================================================
# scripts/check_fresh_clone.sh —— 新克隆自检
# =============================================================================
# 检查：关键文件/数据是否存在、Python 依赖、离线测试是否通过。
# 不依赖 Hadoop / Hive / MySQL（Agent + Web 链路可在纯 Python 环境运行）。
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=============================================================="
echo "  空气质量 Agent · 新克隆自检"
echo "=============================================================="

for f in LICENSE README.md start.sh requirements.txt config.py \
         data/raw/daily/README.md data/raw/chunks/README.md \
         data/cache/cleaned/air_quality_2024-01.csv \
         data/reference/city_province.csv \
         docs/答辩演示.html; do
  if [ ! -e "$f" ]; then
    echo "[失败] 缺少 $f"
    exit 1
  fi
done
echo "[通过] 关键文件与数据齐全"

python3 - <<'PY'
import pandas, matplotlib, pymysql, requests
print("[通过] Python 依赖：pandas / matplotlib / pymysql / requests")
PY

python3 -m unittest discover -s tests
echo "[通过] 自动化测试完成（MySQL 未就绪时对账用例会自动跳过）"
echo "提示：启动前后端执行 ./start.sh（或 ./start.sh --planner=rule）"
