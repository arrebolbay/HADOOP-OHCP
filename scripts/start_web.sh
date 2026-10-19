#!/usr/bin/env bash
# 一键启动网页前端（自动切到项目根目录）
# 用法：./scripts/start_web.sh [--port 8000] [--planner rule]
set -e
cd "$(dirname "$0")/.."
exec python3 web/server.py "$@"
