#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step04_hdfs_upload.py —— 第 4 步：把分片数据上传到 HDFS
================================================================================
为什么要上传 HDFS？
    HDFS 是 Hadoop 的分布式文件系统，后面的 Hive 外部表直接读这里的 CSV，
    MapReduce 也从这里读输入。上传后数据就脱离了"单机文件"的范畴，
    体现大数据平台"存储与计算分离"的基本形态。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, warn, error, print_table, hdfs, hdfs_rmr, hdfs_exists, run


def main():
    banner("第 4 步：上传分片数据到 HDFS")
    raw_chunks = sorted(config.RAW_CHUNK_DIR.glob(f"air_quality_{config.DATASET_YEAR}-*.csv"))
    clean_chunks = sorted(config.CLEAN_CHUNK_DIR.glob(f"air_quality_{config.DATASET_YEAR}-*.csv"))
    if not raw_chunks:
        error("本地没有分片，请先运行 step02_prepare_data.py")
        return 1
    if not clean_chunks:
        warn("还没有清洗后的分片，先上传原始分片（建议先跑 step03）")
        source_chunks = raw_chunks
    else:
        # 关键：Hive / MapReduce 使用清洗后的分片，保证与 Python 计算同源同口径
        source_chunks = clean_chunks
        info(f"使用清洗后的分片作为 ODS 数据源（{len(clean_chunks)} 个），"
             f"原始分片同时上传留档")

    code, _ = hdfs(["ls", "/"], quiet=True)
    if code != 0:
        error("HDFS 不可用。请先启动：/opt/hadoop/sbin/start-dfs.sh && start-yarn.sh")
        return 1
    # 刚启动的 NameNode 可能处于安全模式（只读），这里自动尝试退出一次
    run([f"{config.HADOOP_HOME}/bin/hdfs", "dfsadmin", "-safemode", "leave"],
        quiet=True, filter_noise=True)

    target = f"{config.HDFS_ODS}/air_quality"
    raw_target = f"{config.HDFS_RAW}/air_quality"
    for path_dir in (target, raw_target):
        if hdfs_exists(path_dir):
            hdfs_rmr(path_dir)
        hdfs(["mkdir", "-p", path_dir], quiet=True, check=True)

    rows = []
    for path in source_chunks:
        code, _ = hdfs(["put", str(path), f"{target}/{path.name}"],
                       log_name="04_hdfs.log", quiet=True)
        if code != 0:
            error(f"上传失败：{path.name}")
            return 1
        rows.append((path.name, f"{path.stat().st_size / 1024 / 1024:.1f} MB", "已上传(清洗)"))
    # 原始分片留档（可追溯，不参与 Hive 计算）
    if clean_chunks:
        for path in raw_chunks:
            hdfs(["put", str(path), f"{raw_target}/{path.name}"],
                 log_name="04_hdfs.log", quiet=True)
    print_table(rows, headers=["分片", "大小", "状态"], max_rows=15, title="上传结果")

    # 用 hdfs count 校验文件数与总字节数
    _, out = hdfs(["count", target], quiet=True)
    info("HDFS count：" + " ".join(out.split()[:6]))
    _, ls_out = hdfs(["ls", "-R", target], quiet=True)
    uploaded = [l for l in ls_out.splitlines() if l.strip().endswith(".csv")]
    ok(f"HDFS 上共有 {len(uploaded)} 个分片文件，ODS 路径：{target}")
    info("说明：Hive/MapReduce 读取清洗后的分片，与 Python 计算同源同口径；"
         "原始分片留档在 " + raw_target)
    info("下一步：step05 建立 Hive ODS 外部表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
