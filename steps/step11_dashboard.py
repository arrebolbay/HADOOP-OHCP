#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step11_dashboard.py —— 第 11 步：综合分析看板（4 张图拼一张）
================================================================================
看板内容：
    ① 全国 PM2.5 月度均值走势
    ② PM2.5 年均浓度 TOP10 城市
    ③ 各省份超标城市-天数占比（TOP10）
    ④ 空气质量等级分布（AQI 分级）

输出：output/05_分析看板.png + output/05_图表说明.txt
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, error, print_table
from agent.tools.chart_tool import setup_chinese_font
from core.data_store import DataStore


def main():
    banner("第 11 步：综合分析看板")
    store = DataStore()
    if not store.available():
        error("没有数据分片，请先运行 step02 / step03")
        return 1
    setup_chinese_font()

    daily = store.daily_values("pm25", "mean")
    daily["month"] = daily["date"].str.slice(0, 7)
    national = daily.groupby("month")["value"].mean()
    top = store.annual_mean("pm25", top_n=10)
    province = store.province_exceed("pm25", "24h")["rows"][:10]

    # AQI 等级分布：直接读分片中的 quality 列（分块累计）
    counts = {}
    for chunk in store.iter_chunks(usecols=["quality"]):
        for level, n in chunk["quality"].value_counts().items():
            counts[level] = counts.get(level, 0) + int(n)
    order = ["优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"]
    labels = [l for l in order if l in counts]
    values = [counts[l] for l in labels]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), dpi=130)
    ax = axes[0][0]
    ax.plot(national.index, national.values, marker="o", color="#1F618D")
    ax.set_title("全国 PM2.5 月度均值走势")
    ax.set_ylabel("μg/m³")
    ax.grid(alpha=0.25)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    ax = axes[0][1]
    colors = ["#C0392B" if r["exceeded"] else "#2E86C1"
              for r in top.to_dict("records")]
    ax.bar(top["city"], top["value"], color=colors)
    ax.axhline(35, color="crimson", linestyle="--", linewidth=1,
               label="GB 3095 年均限值 35")
    ax.set_title("PM2.5 年均浓度 TOP10 城市")
    ax.set_ylabel("μg/m³")
    ax.legend(fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    ax = axes[1][0]
    ax.barh([r["province"] for r in province][::-1],
            [r["exceed_days"] for r in province][::-1], color="#E67E22")
    ax.set_title("各省份 PM2.5 超标城市-天数 TOP10")
    ax.set_xlabel("城市-天数")

    ax = axes[1][1]
    palette = ["#00E400", "#FFFF00", "#FF7E00", "#FF0000", "#99004C", "#7E0023"]
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=110,
           colors=palette[:len(values)], textprops={"fontsize": 9})
    ax.set_title("空气质量等级分布（AQI 分级）")

    fig.suptitle(f"{config.DATASET_YEAR} 年空气质量综合分析看板", fontsize=16)
    fig.text(0.99, 0.01, "数据：本地真实监测分片（分片批处理）", ha="right",
             fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    out_png = config.OUTPUT_DIR / "05_分析看板.png"
    fig.savefig(out_png)
    plt.close(fig)
    ok(f"看板已生成：{out_png}")

    note = [
        "图表说明",
        "=" * 50,
        "① 全国 PM2.5 月度均值：先按城市-日求均值（≥12 个有效小时），再对全国取平均。",
        "② TOP10 城市：红线为 GB 3095-2012 年均二级标准 35μg/m³，红色柱表示超标。",
        "③ 各省超标天数：城市日均 PM2.5 > 75μg/m³ 记为一个超标城市-天。",
        "④ 空气质量等级：由 AQI 按 HJ 633-2012 分级统计。",
        "",
        f"TOP1 城市：{top.iloc[0]['city']} {top.iloc[0]['value']:.2f}μg/m³",
        f"全国超标城市-天数：{sum(r['exceed_days'] for r in province):,}（TOP10 省份）",
        "数据来源：" + config.DATASET_SOURCE,
    ]
    out_txt = config.OUTPUT_DIR / "05_图表说明.txt"
    out_txt.write_text("\n".join(note), encoding="utf-8")
    print_table([(r["city"], f"{r['value']:.2f}") for r in top.to_dict("records")],
                headers=["城市", "年均PM2.5"], title="TOP10")
    info(f"图表说明已写入 {out_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
