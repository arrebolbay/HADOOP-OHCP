# -*- coding: utf-8 -*-
"""
common.py —— 公共工具箱（所有步骤脚本、Agent 工具共用）
================================================================================
包含：
    1) 控制台输出：banner / info / ok / warn / error / print_table
    2) 命令执行：run（带日志、噪音过滤、超时）
    3) HDFS / Hive / Sqoop 封装
    4) MySQL 读写（pymysql）
    5) JSON 读写、计时器

为什么单独抽一个文件？
    Hadoop、Hive、MySQL 的调用细节（环境变量、日志噪音、返回码）都很啰嗦，
    集中在这里以后，steps/ 与 agent/tools/ 只需要一行调用，代码更干净、可测试。
"""

import json
import re
import subprocess
import time

from config import (
    HADOOP_HOME, HIVE_HOME, SQOOP_HOME, LOG_DIR, MYSQL_HOST, MYSQL_PORT,
    MYSQL_USER, MYSQL_PASSWORD, ensure_dirs, hadoop_env,
)

# =============================================================================
# 一、控制台输出
# =============================================================================
C_GREEN, C_YELLOW, C_RED, C_BLUE, C_END = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"


def hr(char="=", width=78):
    print(char * width)


def banner(title):
    print()
    hr("=")
    print(f"  {title}")
    hr("=")


def info(msg):
    print(f"{C_BLUE}[信息]{C_END} {msg}")


def ok(msg):
    print(f"{C_GREEN}[成功]{C_END} {msg}")


def warn(msg):
    print(f"{C_YELLOW}[注意]{C_END} {msg}")


def error(msg):
    print(f"{C_RED}[失败]{C_END} {msg}")


def _display_width(text):
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def print_table(rows, headers=None, max_rows=20, title=None):
    """按列宽对齐打印二维表格（中文按 2 个字符宽估算）。"""
    if title:
        print(f"\n{title}")
    rows = list(rows)
    if not rows:
        print("  （空）")
        return
    rows = rows[:max_rows]
    ncol = max(len(r) for r in rows)
    widths = []
    for i in range(ncol):
        values = [str(r[i]) for r in rows if i < len(r)]
        if headers and i < len(headers):
            values.append(str(headers[i]))
        widths.append(max(_display_width(v) for v in values) if values else 4)

    def fmt(row):
        cells = []
        for i, v in enumerate(row):
            text = str(v)
            cells.append(text + " " * max(widths[i] - _display_width(text), 0))
        return " | ".join(cells)

    if headers:
        print(fmt(headers))
        print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))


# =============================================================================
# 二、命令执行
# =============================================================================
_NOISE_RE = re.compile(
    r"^(SLF4J|log4j|WARN |INFO |DEBUG |Hadoop |WARNING: |"
    r"Java HotSpot|OpenJDK|Picked up|NOTE: |Loading|"
    r"which: no|/usr/bin/env: )",
    re.IGNORECASE,
)


def _is_noise(line):
    return bool(_NOISE_RE.match(line.strip()))


def run(cmd, log_name=None, env=None, timeout=None, quiet=False,
        filter_noise=True, check=False):
    """执行 shell 命令，输出并写日志，返回 (返回码, 输出文本)。"""
    ensure_dirs()
    env = env or hadoop_env()
    use_shell = isinstance(cmd, str)
    cmd_display = cmd if use_shell else " ".join(cmd)

    t0 = time.time()
    proc = subprocess.run(
        cmd, shell=use_shell, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=timeout,
    )
    out = proc.stdout or ""
    elapsed = time.time() - t0

    if not quiet:
        print(f"{C_YELLOW}$ {cmd_display}{C_END}")
        for line in out.splitlines():
            if filter_noise and _is_noise(line):
                continue
            if line.strip():
                print("   " + line)

    if log_name:
        with open(LOG_DIR / log_name, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 70}\n[命令] {cmd_display}\n"
                    f"[耗时] {elapsed:.2f}s  [返回码] {proc.returncode}\n"
                    f"{'-' * 70}\n{out}\n")

    if proc.returncode != 0 and check:
        raise RuntimeError(f"命令执行失败（返回码 {proc.returncode}）：{cmd_display}")
    return proc.returncode, out


# =============================================================================
# 三、HDFS / Hive / Sqoop
# =============================================================================
def hdfs(args, log_name=None, **kwargs):
    """执行 HDFS 命令：hdfs(["ls", "/"]) -> hadoop fs -ls /（自动补减号）。"""
    args = list(args)
    if args and not args[0].startswith("-"):
        args[0] = "-" + args[0]
    return run([f"{HADOOP_HOME}/bin/hadoop", "fs"] + args, log_name=log_name, **kwargs)


def hdfs_exists(path):
    code, _ = hdfs(["test", "-e", path], quiet=True, check=False)
    return code == 0


def hdfs_rmr(path, log_name=None):
    return hdfs(["rm", "-r", "-f", path], log_name=log_name)


def hdfs_cat(path, limit=None):
    _, out = hdfs(["cat", path], quiet=True)
    lines = [l for l in out.splitlines() if not _is_noise(l)]
    return "\n".join(lines[:limit] if limit else lines)


HIVE_NOISE = re.compile(
    r"^(OK|Time taken|WARNING|No rows? selected|Compiling|Query ID|"
    r"Fetching|Beginning|Ended|MapReduce|Stage|Launched|Kill|"
    r"Hive Session ID|Logging initialized|"
    r"Total (MapReduce|jobs)|Job\b|Waiting)",
    re.IGNORECASE,
)


def hive_file(sql_path, log_name=None, timeout=3600):
    return run([f"{HIVE_HOME}/bin/hive", "-S", "-f", str(sql_path)],
               log_name=log_name, timeout=timeout)


def hive_query(sql, log_name=None, timeout=1800, show=True):
    return run([f"{HIVE_HOME}/bin/hive", "-S", "-e", sql],
               log_name=log_name, timeout=timeout, quiet=not show)


def hive_rows(sql, timeout=1800):
    """执行 Hive SQL 并按制表符解析成二维列表（过滤客户端提示）。"""
    code, out = hive_query("SET hive.cli.print.header=false;\n" + sql,
                           timeout=timeout, show=False)
    rows = []
    for line in out.splitlines():
        if _is_noise(line) or HIVE_NOISE.match(line.strip()) or not line.strip():
            continue
        rows.append(tuple(c.strip() for c in line.split("\t")))
    return code, rows


def hive_scalar(sql, timeout=1800):
    code, rows = hive_rows(sql, timeout=timeout)
    if code != 0 or not rows:
        return None
    return rows[0][0]


def sqoop(args, log_name=None, timeout=1800, quiet=False):
    return run([f"{SQOOP_HOME}/bin/sqoop"] + list(args),
               log_name=log_name, timeout=timeout, quiet=quiet)


# =============================================================================
# 四、MySQL（pymysql）
# =============================================================================
def mysql_conn(database=None):
    """建立 MySQL 连接；database=None 表示不选库（用于 CREATE DATABASE）。"""
    import pymysql
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
        password=MYSQL_PASSWORD, database=database, charset="utf8mb4",
        autocommit=True, local_infile=True,
    )


def mysql_query(sql, params=None, database=None):
    """查询并返回 dict 行列表。"""
    conn = mysql_conn(database)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def mysql_execute(sql, params=None, database=None, many=False):
    """执行写操作，返回受影响行数（many=True 时 params 是序列）。"""
    conn = mysql_conn(database)
    try:
        with conn.cursor() as cur:
            if many:
                cur.executemany(sql, params or [])
                return cur.rowcount
            cur.execute(sql, params or ())
            return cur.rowcount
    finally:
        conn.close()


def mysql_scalar(sql, params=None, database=None):
    rows = mysql_query(sql, params, database)
    if not rows:
        return None
    return list(rows[0].values())[0]


def mysql_run_file(sql_path, database=None, log_name=None):
    """按分号切分并执行 .sql 文件（适合建表/视图/存储过程脚本）。"""
    text = open(sql_path, encoding="utf-8").read()
    return mysql_run_text(text, database=database, log_name=log_name)


def mysql_run_text(sql_text, database=None, log_name=None):
    """执行多语句 SQL 文本；自动跳过空语句与注释行。"""
    conn = mysql_conn(database)
    executed = 0
    try:
        with conn.cursor() as cur:
            for stmt in _split_sql(sql_text):
                cur.execute(stmt)
                executed += 1
    finally:
        conn.close()
    if log_name:
        with open(LOG_DIR / log_name, "a", encoding="utf-8") as f:
            f.write(f"\n[MySQL] 执行 {sql_path if 'sql_path' in locals() else ''}"
                    f" {executed} 条语句\n")
    return executed


def _split_sql(text):
    """去掉整行注释后按分号切分（本项目 SQL 里不写存储过程体内的分号）。"""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    cleaned = "\n".join(lines)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


# =============================================================================
# 五、JSON / 杂项
# =============================================================================
def save_json(data, path):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return str(path)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Timer:
    """with Timer() as t: ...  then t.elapsed 秒。"""

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.time() - self.t0
        return False
