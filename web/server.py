#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web/server.py —— 零依赖本地 Web 服务（Python 标准库 http.server）
================================================================================
启动：
    python3 web/server.py                 # http://127.0.0.1:8000
    python3 web/server.py --port 8080
    python3 web/server.py --planner rule  # 强制规则规划器（无网演示）

接口：
    GET  /                 前端页面
    GET  /static/*         静态资源（CSS / JS）
    GET  /api/health       环境与数据状态
    GET  /api/overview     数据概览（规模 / TOP5 / 省份超标 / 清洗 / 测试）
    POST /api/ask          {"question": "...", "planner": "auto|rule"}
    POST /api/reset        清空多轮记忆
    GET  /charts/<file>    分析生成的 PNG 图表

设计说明：
    * 不引入 Flask/FastAPI，比赛现场少一个依赖、少一个安装失败点；
    * Agent 在服务端常驻，天然支持网页上的多轮追问（共享 Memory）；
    * 所有计算仍由本地工具完成，前端只负责展示，不伪造任何数字。
"""

import argparse
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import sys

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import config
from agent import AirQualityAgent
from agent.memory import Memory
from agent.planner import DualPlanner, LLMPlanner, RulePlanner, get_planner
from common import load_json, mysql_scalar
from core.data_store import DataStore

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

MIME = {"html": "text/html; charset=utf-8", "css": "text/css; charset=utf-8",
        "js": "application/javascript; charset=utf-8", "png": "image/png",
        "svg": "image/svg+xml", "ico": "image/x-icon"}


def _mysql_status():
    try:
        rows = mysql_scalar("SELECT COUNT(*) FROM fact_city_year",
                            database=config.MYSQL_DB)
        return {"connected": True, "fact_rows": int(rows or 0)}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": str(exc)[:120]}


def _test_status():
    path = config.OUTPUT_DIR / "test_report.txt"
    if not path.exists():
        return {"available": False}
    text = path.read_text(encoding="utf-8", errors="ignore")
    ran = None
    for line in text.splitlines():
        if line.startswith("Ran ") and " test" in line:
            try:
                ran = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    tail = "\n".join(text.splitlines()[-6:])
    return {"available": True, "ran": ran,
            "passed": ("OK" in tail and "FAILED" not in tail),
            "updated": int(path.stat().st_mtime)}


def build_overview(store):
    if not store.available():
        return {"available": False, "message": "尚未准备数据，请先运行 step02/step03"}
    stats = store.stats()
    top = store.annual_mean("pm25", top_n=5).to_dict("records")
    province = store.province_exceed("pm25", "24h")
    return {
        "available": True,
        "stats": stats,
        "top_cities": [{"city": r["city"], "province": r["province"],
                        "value": round(float(r["value"]), 1),
                        "exceeded": bool(r["exceeded"])} for r in top],
        "province_top": [{"province": r["province"],
                          "exceed_days": int(r["exceed_days"]),
                          "share": round(float(r["share"]), 3)}
                         for r in province["rows"][:6]],
        "total_exceed_days": province["total_exceed_days"],
        "cleaning": load_json(config.OUTPUT_DIR / "cleaning_report.json", {}),
        "tests": _test_status(),
        "mysql": _mysql_status(),
        "dataset": {"name": config.DATASET_NAME, "source": config.DATASET_SOURCE,
                    "year": config.DATASET_YEAR},
    }


def _planner_for(mode):
    mode = (mode or "auto").lower()
    if mode == "rule":
        return RulePlanner()
    if mode == "llm":
        return LLMPlanner()
    return DualPlanner()


def create_server(host="127.0.0.1", port=8000, store=None, planner=None,
                  verbose=False):
    """可注入 store/planner 的服务器工厂（便于自动化测试）。"""
    store = store or DataStore()
    default_planner = planner
    agent = AirQualityAgent(store=store, planner=default_planner or get_planner(),
                            verbose=verbose)
    lock = threading.Lock()
    cache = {"overview": None}

    class Handler(BaseHTTPRequestHandler):
        server_version = "AirQualityAgent/1.0"

        def log_message(self, fmt, *args):  # 静默访问日志
            return

        # ------------------------- 基础响应 -------------------------
        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path, content_type=None):
            try:
                data = Path(path).read_bytes()
            except OSError:
                self._json({"error": "文件不存在"}, 404)
                return
            ctype = content_type or MIME.get(Path(path).suffix.lstrip("."),
                                             "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ------------------------- GET -------------------------
        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            try:
                if path in ("/", "/index.html"):
                    self._file(STATIC_DIR / "index.html", MIME["html"])
                elif path.startswith("/static/"):
                    self._static(path[len("/static/"):])
                elif path == "/api/health":
                    self._json({
                        "ok": True,
                        "planner_mode": getattr(agent.planner, "name", config.PLANNER_MODE),
                        "llm_ready": bool(config.LLM_API_KEY),
                        "data": {"available": store.available(),
                                 "chunks": len(store.chunk_files()),
                                 "cleaned": store.is_cleaned()},
                        "mysql": _mysql_status(),
                        "dataset": config.DATASET_NAME,
                    })
                elif path == "/api/overview":
                    with lock:
                        if cache["overview"] is None:
                            cache["overview"] = build_overview(store)
                        payload = cache["overview"]
                    self._json(payload)
                elif path.startswith("/charts/"):
                    name = Path(path[len("/charts/"):]).name
                    self._file(config.CHART_DIR / name, MIME["png"])
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)

        def _static(self, rel):
            rel = Path(rel)
            if ".." in rel.parts:
                self._json({"error": "forbidden"}, 403)
                return
            self._file(STATIC_DIR / rel)

        # ------------------------- POST -------------------------
        def do_POST(self):
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length > 100_000:
                    self._json({"error": "请求过大"}, 413)
                    return
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                self._json({"error": "请求体不是合法 JSON"}, 400)
                return

            try:
                if path == "/api/ask":
                    question = str(body.get("question", "")).strip()[:500]
                    if not question:
                        self._json({"error": "问题不能为空"}, 400)
                        return
                    if not store.available():
                        self._json({"error": "本地数据未就绪，请先运行 step02 / step03"}, 400)
                        return
                    mode = str(body.get("planner", "auto"))
                    with lock:
                        # 未显式切换时沿用注入/默认规划器（便于测试与部署配置）
                        agent.planner = (default_planner if (mode == "auto" and default_planner)
                                         else _planner_for(mode))
                        result = agent.ask(question)
                    charts = [{"url": "/charts/" + Path(c["path"]).name,
                               "title": c["title"]} for c in result["charts"]]
                    self._json({
                        "question": result["question"],
                        "answer": result["answer"],
                        "planner": result["plan"].get("planner"),
                        "intent": result["plan"].get("intent"),
                        "slots": result["plan"].get("slots", {}),
                        "trace": result["trace"],
                        "charts": charts,
                        "validation": result["validation"],
                        "elapsed_s": round(sum(t["elapsed_s"] for t in result["trace"]), 2),
                        "memory": agent.memory.context(),
                    })
                elif path == "/api/reset":
                    with lock:
                        agent.memory = Memory()
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                print(traceback.format_exc(limit=3))
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def main():
    parser = argparse.ArgumentParser(description="空气质量 Agent Web 前端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--planner", default=config.PLANNER_MODE,
                        choices=["auto", "rule", "llm"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    server = create_server(args.host, args.port,
                           planner=_planner_for(args.planner),
                           verbose=args.verbose)
    print("=" * 70)
    print("  空气质量时序分析 Agent · Web 前端")
    print(f"  地址：http://{args.host}:{args.port}")
    print(f"  规划器：{args.planner}｜大模型 Key："
          f"{'已配置' if config.LLM_API_KEY else '未配置（规则兜底）'}")
    print(f"  数据：{config.DATASET_NAME}")
    print("  按 Ctrl+C 停止")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 Web 服务")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

