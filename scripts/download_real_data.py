#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/download_real_data.py —— 下载真实公开空气质量数据（赛前准备用）
================================================================================
数据来源：https://quotsoft.net/air/ （全国城市空气质量实时发布平台公开日文件，
          原始数据源为 中国环境监测总站 / 国家城市空气质量实时发布平台）
文件格式：china_cities_YYYYMMDD.csv，日期+小时+指标类型+全国 370+ 城市列
          指标类型：AQI / PM2.5 / PM10 / SO2 / NO2 / CO / O3（含 24h、8h 变体）

【什么时候运行？】
    比赛前（有网时）运行一次，把 2024 全年数据落到 data/raw/daily/。
    比赛现场只读本地文件，不再联网（满足题目"现场不依赖网络下载数据"）。

【用法】
    python3 scripts/download_real_data.py --start 2024-01-01 --end 2024-12-31
    python3 scripts/download_real_data.py --start 2024-01-01 --end 2024-01-31  # 小样本

【说明】
    已存在且校验通过的文件会自动跳过，中断后重跑可续传。
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_DIR / "data" / "raw" / "daily"
BASE_URL = "https://quotsoft.net/air/data/china_cities_{}.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (air-quality-agent contest data prep)"}


def is_valid(path: Path) -> bool:
    """校验已下载文件：表头正确 + 行数 >= 300（15 种指标 × 24 小时）。"""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            first = f.readline()
            if not first.startswith("date,hour,type,"):
                return False
            return sum(1 for _ in f) >= 300
    except OSError:
        return False


def download_day(day: date, retries: int = 3) -> Path:
    """下载某一天的文件，返回本地路径；已存在则直接返回。"""
    name = f"china_cities_{day:%Y%m%d}.csv"
    out = OUT_DIR / name
    if is_valid(out):
        return out
    tmp = out.with_suffix(".tmp")
    url = BASE_URL.format(f"{day:%Y%m%d}")
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            if len(resp.content) < 1024:
                raise ValueError(f"内容过小（{len(resp.content)} 字节）")
            tmp.write_bytes(resp.content)
            if not is_valid(tmp):
                raise ValueError("表头或行数校验失败")
            tmp.replace(out)
            return out
        except Exception as exc:  # noqa: BLE001 - 网络异常统一重试
            if attempt == retries:
                raise RuntimeError(f"下载失败 {name}: {exc}") from exc
            time.sleep(attempt * 2)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 2024 全国城市空气质量真实数据")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--sleep", type=float, default=0.15, help="每次请求间隔秒数")
    parser.add_argument("--workers", type=int, default=1,
                        help="并发下载线程数（默认 1；赶时间可用 6~8）")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        print("起始日期不能晚于结束日期")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = (end - start).days + 1
    days = [start + timedelta(days=i) for i in range(total)]
    print(f"开始下载 {start} ~ {end} 共 {total} 个文件 -> {OUT_DIR}"
          f"（并发 {args.workers}）")

    if args.workers <= 1:
        ok = skipped = failed = 0
        for i, day in enumerate(days, 1):
            name = f"china_cities_{day:%Y%m%d}.csv"
            existed = is_valid(OUT_DIR / name)
            try:
                download_day(day)
                if existed:
                    skipped += 1
                else:
                    ok += 1
                    print(f"[{i}/{total}] 已下载 {name}")
            except Exception as exc:  # noqa: BLE001 - 单日失败不影响整体
                failed += 1
                print(f"[{i}/{total}] 失败 {name}: {exc}")
            time.sleep(args.sleep)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        ok = skipped = failed = 0

        def task(day):
            name = f"china_cities_{day:%Y%m%d}.csv"
            existed = is_valid(OUT_DIR / name)
            download_day(day)
            return day, existed

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(task, d): d for d in days}
            for i, future in enumerate(as_completed(futures), 1):
                day = futures[future]
                try:
                    _, existed = future.result()
                    if existed:
                        skipped += 1
                    else:
                        ok += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"失败 {day}: {exc}")
                if i % 20 == 0 or i == total:
                    print(f"[{i}/{total}] 新增 {ok}，已存在 {skipped}，失败 {failed}",
                          flush=True)

    print(f"完成：新增 {ok}，已存在 {skipped}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
