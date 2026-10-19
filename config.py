# -*- coding: utf-8 -*-
"""
config.py —— 空气质量时序分析 Agent 的「配置中心」
================================================================================
所有会随环境变化的东西（路径、Hadoop/MySQL 账号、模型 API、年份）都集中在这里，
换机器只改这一个文件。

【目录约定】
    OHCP/                       ← 项目根目录
      data/raw/daily/           ← 赛前下载的真实日文件（每天一个 CSV）
      data/raw/chunks/          ← 第 2 步整理出的按月分片长表（未清洗）
      data/cache/cleaned/       ← 清洗后的分片（Agent 默认读这里）
      data/reference/           ← 城市→省份参考表
      data/fonts/               ← 绘图用中文字体
      output/charts/            ← Agent 生成的图表
      output/                   ← 报告、对账结果、测试报告
      logs/                     ← 每一步的运行日志

【现场演示原则】
    比赛现场只读本地文件，不联网下载数据；大模型 API 仅用于任务规划，
    没有 Key 时自动使用规则规划器（RulePlanner），全链路照样跑通。
"""

import os
from pathlib import Path

# =============================================================================
# 一、目录结构
# =============================================================================
PROJECT_DIR = Path(__file__).resolve().parent

DATA_DIR = PROJECT_DIR / "data"
RAW_DAILY_DIR = DATA_DIR / "raw" / "daily"          # 每日原始宽表
RAW_CHUNK_DIR = DATA_DIR / "raw" / "chunks"         # 清洗前的按月分片
CLEAN_CHUNK_DIR = DATA_DIR / "cache" / "cleaned"    # 清洗后的按月分片
REFERENCE_DIR = DATA_DIR / "reference"
PROVINCE_MAP_CSV = REFERENCE_DIR / "city_province.csv"
FONT_DIR = DATA_DIR / "fonts"
FONT_FILE = FONT_DIR / "simhei.ttf"
FALLBACK_FONT = PROJECT_DIR.parent / "data" / "fonts" / "simhei.ttf"

OUTPUT_DIR = PROJECT_DIR / "output"
CHART_DIR = OUTPUT_DIR / "charts"
LOG_DIR = PROJECT_DIR / "logs"
STEPS_DIR = PROJECT_DIR / "steps"
SQL_DIR = PROJECT_DIR / "sql"
HIVE_SQL_DIR = SQL_DIR / "hive"
MYSQL_SQL_DIR = SQL_DIR / "mysql"
MR_DIR = PROJECT_DIR / "mapreduce"
TEST_DIR = PROJECT_DIR / "tests"
FIXTURE_DIR = TEST_DIR / "fixtures"

# =============================================================================
# 二、数据集约定（真实公开数据）
# =============================================================================
# 主数据源：阿里云天池「全国空气质量监测数据集」(dataId=14038)，赛前下载后放到 data/raw/tianchi/
# 现场默认数据：quotsoft.net/air 的全国城市空气质量日文件（原始来源：中国环境监测总站
#              国家城市空气质量实时发布平台），已下载到 data/raw/daily/
DATASET_YEAR = int(os.environ.get("AQ_YEAR", "2024"))
DATASET_NAME = "全国城市空气质量2024（真实公开数据）"
DATASET_SOURCE = "全国城市空气质量实时发布平台（quotsoft.net/air 公开日文件）"
TIANCHI_URL = "https://tianchi.aliyun.com/dataset/dataDetail?dataId=14038"

# 原始宽表里的指标类型（24h/8h 变体由我们自己按国标口径计算，不直接使用）
RAW_TYPES = ["AQI", "PM2.5", "PM10", "SO2", "NO2", "CO", "O3"]

# 长表列名 -> 中文名 / 单位（CO 为 mg/m³，其余为 μg/m³）
POLLUTANTS = {
    "pm25": {"cn": "PM2.5", "unit": "μg/m³"},
    "pm10": {"cn": "PM10", "unit": "μg/m³"},
    "so2": {"cn": "SO₂", "unit": "μg/m³"},
    "no2": {"cn": "NO₂", "unit": "μg/m³"},
    "o3": {"cn": "O₃", "unit": "μg/m³"},
    "co": {"cn": "CO", "unit": "mg/m³"},
    "aqi": {"cn": "AQI", "unit": ""},
}

# 每个指标的物理合理范围（超出视为异常值，清洗时置空/截断）
PHYSICAL_RANGES = {
    "pm25": (0, 1000), "pm10": (0, 1500), "so2": (0, 2000), "no2": (0, 1000),
    "co": (0, 50), "o3": (0, 1000), "aqi": (0, 500),
}

# 季节定义（月份）
SEASONS = {
    "春季": [3, 4, 5],
    "夏季": [6, 7, 8],
    "秋季": [9, 10, 11],
    "冬季": [12, 1, 2],
}

# =============================================================================
# 三、Hadoop / Hive / Sqoop（与工作区已有大数据环境保持一致）
# =============================================================================
HADOOP_HOME = "/opt/hadoop"
HIVE_HOME = "/opt/hive"
SQOOP_HOME = "/opt/sqoop"
JAVA_HOME = "/usr/lib/jvm/java-8-openjdk-amd64"
STREAMING_JAR = f"{HADOOP_HOME}/share/hadoop/tools/lib/hadoop-streaming-3.3.6.jar"

# HDFS 上的目录规划（ODS -> DWD -> DWS -> ADS）
HDFS_ROOT = "/air_quality"
HDFS_RAW = f"{HDFS_ROOT}/raw"            # 原始分片（留档审计）
HDFS_ODS = f"{HDFS_ROOT}/ods"
HDFS_DWD = f"{HDFS_ROOT}/dwd"
HDFS_DWS = f"{HDFS_ROOT}/dws"
HDFS_ADS = f"{HDFS_ROOT}/ads"
HDFS_MR = f"{HDFS_ROOT}/mapreduce"
HDFS_SQOOP = f"{HDFS_ROOT}/sqoop"

HIVE_DB = "air_quality"
HDFS_USER = os.environ.get("HDFS_USER") or "bayern"

# =============================================================================
# 四、MySQL（结果库：给 Agent 快速查询、给前端展示）
# =============================================================================
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "aq_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "aq_pass_2026")
MYSQL_DB = os.environ.get("MYSQL_DB", "air_quality")
# auto = 有 ADS 结果表就直接查 MySQL，没有就用本地分片计算
DATA_BACKEND = os.environ.get("AQ_BACKEND", "auto")

# =============================================================================
# 五、Agent / 大模型（双模：API 优先 + 规则兜底）
# =============================================================================
# AQ_PLANNER: auto = 有 Key 先试 LLM，失败自动降级；rule = 强制规则；llm = 强制大模型
PLANNER_MODE = os.environ.get("AQ_PLANNER", "auto")
LLM_BASE_URL = os.environ.get("AQ_LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("AQ_LLM_MODEL", "deepseek-chat")
LLM_API_KEY = os.environ.get("AQ_LLM_API_KEY", "")
LLM_TIMEOUT = float(os.environ.get("AQ_LLM_TIMEOUT", "8"))
LLM_MAX_RETRIES = 1

# 报告模板：simple = 面向公众的简易解读版；pro = 面向从业者的专业统计版
REPORT_TEMPLATE = os.environ.get("AQ_REPORT", "simple")

# 校验 / 业务阈值
VALIDATE_MAX_REL_DIFF = 0.02      # 本地复算 vs MySQL 结果允许的相对误差
ALERT_MOM_CHANGE = 0.40           # 月度环比变化超过 40% 视为突变
ALERT_MIN_DIFF = 10.0             # 且绝对变化不低于 10（μg/m³ 或 mg/m³）
DAILY_MIN_HOURS = 12              # 日均值至少需要 12 个有效小时
O3_MIN_HOURS = 6                  # 日最大 8 小时均值至少需要 6 个有效小时

# =============================================================================
# 六、工具函数
# =============================================================================
def ensure_dirs():
    """一次性创建所有输出目录（幂等，随便调）。"""
    for d in (DATA_DIR, RAW_DAILY_DIR, RAW_CHUNK_DIR, CLEAN_CHUNK_DIR, REFERENCE_DIR,
              FONT_DIR, OUTPUT_DIR, CHART_DIR, LOG_DIR, FIXTURE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def hadoop_env():
    """返回带 Hadoop/Java 环境变量的 os.environ 副本（每个子进程命令都用它）。"""
    env = os.environ.copy()
    env.update({
        "JAVA_HOME": JAVA_HOME,
        "HADOOP_HOME": HADOOP_HOME,
        "HIVE_HOME": HIVE_HOME,
        "HADOOP_USER_NAME": HDFS_USER,
        "HADOOP_CONF_DIR": f"{HADOOP_HOME}/etc/hadoop",
        "HADOOP_CLIENT_OPTS": f"-Xmx2g {env.get('HADOOP_CLIENT_OPTS', '')}".strip(),
        "PATH": f"{HADOOP_HOME}/bin:{HADOOP_HOME}/sbin:{HIVE_HOME}/bin:"
                f"{SQOOP_HOME}/bin:{env.get('PATH', '')}",
    })
    return env


def font_path():
    """返回可用的中文字体路径（首次克隆仓库时自动尝试系统中文字体）。"""
    candidates = [
        FONT_FILE,
        FONT_DIR / "wqy-microhei.ttc",
        FALLBACK_FONT,
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/mnt/c/Windows/Fonts/msyh.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    return None


ensure_dirs()

