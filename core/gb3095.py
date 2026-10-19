# -*- coding: utf-8 -*-
"""
core/gb3095.py —— 《环境空气质量标准》GB 3095—2012 判定规则（二级标准）
================================================================================
为什么单独做一个模块？
    国标判定是业务正确性的核心，必须"唯一来源"：Agent 工具、Hive SQL、MySQL 视图、
    图表注释都引用同一套限值，避免各写一份导致口径不一致。

【本项目采用的二级标准限值】
    污染物     年均      24 小时平均     日最大 8 小时平均
    PM2.5      35        75              —
    PM10       70        150             —
    SO₂        60        150             —
    NO₂        40        80              —
    CO         —         4 mg/m³         —
    O₃         —         —               160

【判定口径】
    《标准》中的"超标"指监测值 **超过** 限值，因此 value == limit 视为达标；
    比较时加一个极小量（1e-9）规避浮点误差。
"""

from config import POLLUTANTS

# 二级标准限值（CO 单位 mg/m³，其余 μg/m³）
LIMITS = {
    "pm25": {"annual": 35.0, "24h": 75.0},
    "pm10": {"annual": 70.0, "24h": 150.0},
    "so2": {"annual": 60.0, "24h": 150.0},
    "no2": {"annual": 40.0, "24h": 80.0},
    "co": {"24h": 4.0},
    "o3": {"8h": 160.0},
}

PERIOD_CN = {"annual": "年均", "24h": "24小时平均", "8h": "日最大8小时平均"}

AQI_LEVELS = [
    (0, 50, "优", "空气质量令人满意，基本无空气污染"),
    (51, 100, "良", "空气质量可接受，极少数敏感人群应减少户外活动"),
    (101, 150, "轻度污染", "易感人群症状轻度加剧，建议减少长时间户外锻炼"),
    (151, 200, "中度污染", "进一步加剧易感人群症状，建议减少户外活动"),
    (201, 300, "重度污染", "健康人群运动耐受力降低，建议停止户外活动"),
    (301, 500, "严重污染", "健康人群普遍出现症状，应避免户外活动"),
]


def pollutant_cn(metric):
    """pm25 -> 'PM2.5'；未知指标原样返回。"""
    return POLLUTANTS.get(metric, {}).get("cn", metric)


def unit_of(metric):
    return POLLUTANTS.get(metric, {}).get("unit", "")


def limit_of(metric, period="annual"):
    """返回限值；该指标没有该统计口径时返回 None。"""
    return LIMITS.get(metric, {}).get(period)


def judged_periods(metric):
    """该指标有哪些可用判定口径（用于自动选择）。"""
    return list(LIMITS.get(metric, {}).keys())


def choose_period(metric, preferred=None):
    """优先用调用方指定的口径；不支持则退回该指标的第一个口径。"""
    periods = judged_periods(metric)
    if preferred in periods:
        return preferred
    return periods[0] if periods else None


def judge(value, metric, period="annual", level="二级"):
    """
    判定单个数值是否超标。

    返回 dict：value / metric / period / limit / exceeded / ratio / text
        ratio = value / limit（便于排序和展示"超标倍数"）
    """
    limit = limit_of(metric, period)
    if limit is None or value is None:
        return {
            "value": value, "metric": metric, "period": period,
            "limit": limit, "exceeded": False, "ratio": None,
            "text": f"{pollutant_cn(metric)} 缺少{PERIOD_CN.get(period, period)}限值",
        }
    exceeded = float(value) > limit + 1e-9
    ratio = float(value) / limit if limit else None
    unit = unit_of(metric)
    cmp_text = "超过" if exceeded else "未超过"
    text = (f"{pollutant_cn(metric)}{PERIOD_CN.get(period, period)}浓度 "
            f"{float(value):.2f}{unit}，{cmp_text} GB 3095-2012 {level}标准"
            f"（{PERIOD_CN.get(period, period)}限值 {limit:g}{unit}）")
    return {
        "value": float(value), "metric": metric, "period": period,
        "limit": limit, "exceeded": exceeded, "ratio": ratio, "text": text,
    }


def quality_level(aqi):
    """按 HJ 633-2012 由 AQI 得到空气质量等级、描述与建议。"""
    if aqi is None:
        return {"aqi": None, "level": "未知", "advice": "", "color": "#999999"}
    value = float(aqi)
    for low, high, name, advice in AQI_LEVELS:
        if low <= value <= high:
            color = {"优": "#00E400", "良": "#FFFF00", "轻度污染": "#FF7E00",
                     "中度污染": "#FF0000", "重度污染": "#99004C",
                     "严重污染": "#7E0023"}[name]
            return {"aqi": value, "level": name, "advice": advice, "color": color}
    return {"aqi": value, "level": "严重污染", "advice": "浓度极端偏高，应避免户外活动",
            "color": "#7E0023"}


def standard_brief(metric, period):
    """一句国标科普：用于研判说明（课程思政的自然融入点）。"""
    limit = limit_of(metric, period)
    if limit is None:
        return ""
    return (f"依据《环境空气质量标准》GB 3095—2012，{pollutant_cn(metric)}"
            f"{PERIOD_CN.get(period, period)}二级标准限值为 {limit:g}{unit_of(metric)}；"
            f"监测值超过该限值即判定为超标。")


def eco_tip(exceeded=True):
    """
    1~2 行"环境小感悟"（跟着业务结果走，不弹窗、不说教）：
    超标时强调治理与科技报国；未超标时强调守护与持续监测。
    """
    if exceeded:
        return ("大气监测时序大数据为污染溯源与精准治理提供重要支撑；"
                "绿水青山就是金山银山，新时代青年可以用 Agent 与大数据技术守护蓝天、"
                "服务美丽中国建设。")
    return ("空气质量改善来之不易，持续的大数据监测让治理有据可依；"
            "把论文写在祖国大地上，用技术守护绿水青山。")


def health_card(metric, level):
    """重度及以上污染时附带的污染物危害科普小卡片（创新点：污染科普卡片）。"""
    if level not in {"重度污染", "严重污染"}:
        return ""
    harm = {
        "pm25": "PM2.5 可深入肺泡并进入血液循环，长期暴露增加呼吸系统与心血管疾病风险。",
        "pm10": "PM10 可进入呼吸道深处，易诱发咳嗽、哮喘等呼吸道症状。",
        "o3": "近地面臭氧具有强氧化性，会刺激眼睛和呼吸道，午后高温时段浓度通常最高。",
        "no2": "NO₂ 主要来自机动车与燃烧源，长期暴露会损害呼吸系统。",
        "so2": "SO₂ 易溶于水，会刺激上呼吸道，并参与二次颗粒物生成。",
        "co": "CO 与血红蛋白结合能力强，高浓度会造成组织缺氧。",
    }.get(metric, "高浓度污染天气请减少户外活动，敏感人群做好防护。")
    return f"污染科普：{harm}"
