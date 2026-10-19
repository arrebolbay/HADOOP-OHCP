# -*- coding: utf-8 -*-
"""
core/data_store.py —— 分片数据引擎（Agent 所有计算的唯一数据入口）
================================================================================
设计要点（对应题目"大数据工程体现"）：
    1) 数据按月分片存放（data/raw/chunks、data/cache/cleaned），
       **任何统计都按分片逐块读取**，不把全年 300 多万行一次性载入内存；
    2) 日均/日最大8小时等指标按国标口径计算，并缓存成小文件（data/cache/daily_*），
       之后的聚合查询只读缓存，秒级响应；
    3) 清洗、聚合、异常检测全部是纯函数式实现，可被单元测试直接调用。

长表字段：city, province, date(YYYY-MM-DD), hour, pm25, pm10, so2, no2, co, o3, aqi, quality
"""

import json
from pathlib import Path

import pandas as pd

import config

NUMERIC_COLS = ["pm25", "pm10", "so2", "no2", "co", "o3", "aqi"]

DTYPES = {
    "city": "string", "province": "string", "date": "string", "hour": "int16",
    "quality": "string",
    **{c: "float32" for c in NUMERIC_COLS},
}


class DataStore:
    """按年月分片读取本地真实数据，并提供国标口径的聚合结果。"""

    def __init__(self, chunk_dir=None, year=None):
        self.year = int(year or config.DATASET_YEAR)
        if chunk_dir is not None:
            self.chunk_dir = Path(chunk_dir)
        else:
            cleaned = self._files(config.CLEAN_CHUNK_DIR)
            self.chunk_dir = config.CLEAN_CHUNK_DIR if cleaned else config.RAW_CHUNK_DIR
        # 缓存按分片目录隔离（cleaned / chunks / 测试 fixture 各用各的，避免串味）
        self.cache_dir = config.DATA_DIR / "cache" / f"cache_{self.chunk_dir.name}"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._stats = None
        self._daily_cache = {}

    # ------------------------------------------------------------------
    # 基础：分片发现 / 逐块读取
    # ------------------------------------------------------------------
    def _files(self, folder):
        folder = Path(folder)
        if not folder.exists():
            return []
        return sorted(folder.glob(f"air_quality_{self.year}-*.csv"))

    def chunk_files(self):
        """当前生效的分片文件列表（清洗后的优先）。"""
        return self._files(self.chunk_dir)

    def available(self):
        return bool(self.chunk_files())

    def is_cleaned(self):
        return self.chunk_dir.resolve() == config.CLEAN_CHUNK_DIR.resolve()

    def use_cleaned_if_available(self):
        """清洗完成后切换到 cleaned 分片（Agent 的 clean 工具调用后使用）。"""
        if self._files(config.CLEAN_CHUNK_DIR):
            changed = self.chunk_dir != config.CLEAN_CHUNK_DIR
            self.chunk_dir = config.CLEAN_CHUNK_DIR
            if changed:
                self._stats = None
                self._daily_cache = {}
            return True
        return False

    def iter_chunks(self, usecols=None):
        """逐块读取分片：这是全项目唯一的"读数据"入口。"""
        cols = usecols or list(DTYPES)
        dtypes = {c: DTYPES[c] for c in cols if c in DTYPES}
        for path in self.chunk_files():
            yield pd.read_csv(path, usecols=cols, dtype=dtypes)

    # ------------------------------------------------------------------
    # 数据概况（dataset_read_tool 用）
    # ------------------------------------------------------------------
    def stats(self, refresh=False):
        if self._stats is not None and not refresh:
            return self._stats
        cache_file = self.cache_dir / f"store_stats_{self.year}.json"
        files = self.chunk_files()
        if not files:
            self._stats = {"available": False, "chunks": 0, "rows": 0,
                           "cities": 0, "provinces": 0,
                           "source": str(self.chunk_dir)}
            return self._stats

        mtime = max(p.stat().st_mtime for p in files)
        if (not refresh and cache_file.exists()
                and cache_file.stat().st_mtime >= mtime):
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["source"] = str(self.chunk_dir)
            cached["cleaned"] = self.is_cleaned()
            self._stats = cached
            return cached

        rows = 0
        cities, provinces = set(), set()
        date_min, date_max = "9999-99-99", "0000-00-00"
        missing = {c: 0 for c in NUMERIC_COLS}
        for df in self.iter_chunks():
            rows += len(df)
            cities.update(df["city"].dropna().unique().tolist())
            provinces.update(df["province"].dropna().unique().tolist())
            date_min = min(date_min, str(df["date"].min()))
            date_max = max(date_max, str(df["date"].max()))
            for c in NUMERIC_COLS:
                missing[c] += int(df[c].isna().sum())

        stats = {
            "available": True,
            "dataset": config.DATASET_NAME,
            "year": self.year,
            "source": str(self.chunk_dir),
            "cleaned": self.is_cleaned(),
            "chunks": len(files),
            "rows": rows,
            "cities": len(cities),
            "provinces": len(provinces),
            "date_min": date_min,
            "date_max": date_max,
            "size_mb": round(sum(p.stat().st_size for p in files) / 1024 / 1024, 1),
            "missing_ratio": {c: round(v / rows, 4) if rows else 0
                              for c, v in missing.items()},
        }
        cache_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        self._stats = stats
        return stats

    # ------------------------------------------------------------------
    # 日均值 / 日最大 8 小时均值（带缓存）
    # ------------------------------------------------------------------
    def daily_values(self, metric, agg="mean"):
        """
        返回 DataFrame[city, province, date, value, valid_hours]。
            agg='mean'   : 24 小时算术平均（要求至少 12 个有效小时）
            agg='max8h'  : 日最大 8 小时滑动平均（O₃ 专用）
        """
        key = (metric, agg)
        if key in self._daily_cache:
            return self._daily_cache[key]

        cache_file = self.cache_dir / f"daily_{self.year}_{metric}_{agg}.csv.gz"
        files = self.chunk_files()
        if not files:
            raise FileNotFoundError(
                f"没有找到 {self.year} 年的数据分片：{self.chunk_dir}\n"
                f"请先运行 python3 steps/step02_prepare_data.py")
        newest = max(p.stat().st_mtime for p in files)
        if cache_file.exists() and cache_file.stat().st_mtime >= newest:
            df = pd.read_csv(cache_file, dtype={"date": "string"})
            self._daily_cache[key] = df
            return df

        frames = [self._daily_from_chunk(c, metric, agg) for c in self.iter_chunks()]
        df = pd.concat(frames, ignore_index=True).dropna(subset=["value"])
        df["date"] = df["date"].astype(str)
        df.to_csv(cache_file, index=False)
        self._daily_cache[key] = df
        return df

    def _daily_from_chunk(self, chunk, metric, agg):
        if agg == "max8h":
            return self._max8h(chunk, metric)
        grouped = (chunk.groupby(["city", "province", "date"])[metric]
                   .agg(value="mean", valid_hours="count")
                   .reset_index())
        return grouped[grouped["valid_hours"] >= config.DAILY_MIN_HOURS]

    def _max8h(self, chunk, metric):
        """按 (city, date) 把 24 小时展成一行，滚动 8 小时求最大值。"""
        chunk = chunk.dropna(subset=[metric])
        pivot = chunk.pivot_table(index=["city", "province", "date"],
                                  columns="hour", values=metric, aggfunc="mean")
        pivot = pivot.reindex(columns=list(range(24)))
        valid = pivot.notna().sum(axis=1)
        series = (pivot.T.rolling(window=8,
                                  min_periods=config.O3_MIN_HOURS)
                  .max().T.max(axis=1))
        out = series.rename("value").reset_index()
        out["valid_hours"] = valid.values
        return out[out["value"].notna()]

    # ------------------------------------------------------------------
    # 聚合分析
    # ------------------------------------------------------------------
    def annual_mean(self, metric, top_n=None):
        """城市年均浓度（先日均、再年均），并附国标年均判定。"""
        from core import gb3095
        daily = self.daily_values(metric, "mean")
        agg = (daily.groupby(["city", "province"])
               .agg(value=("value", "mean"), days=("value", "size"))
               .reset_index())
        limit = gb3095.limit_of(metric, "annual")
        agg["limit"] = limit
        if limit:
            agg["exceeded"] = agg["value"] > limit + 1e-9
            agg["ratio"] = agg["value"] / limit
        else:
            agg["exceeded"] = False
            agg["ratio"] = None
        agg = agg.sort_values("value", ascending=False).reset_index(drop=True)
        if top_n:
            agg = agg.head(int(top_n)).reset_index(drop=True)
        return agg

    def monthly_series(self, cities, metric):
        """指定城市逐月均值（用于折线图）。"""
        daily = self.daily_values(metric, "mean")
        daily = daily[daily["city"].isin(list(cities))].copy()
        daily["month"] = daily["date"].str.slice(0, 7)
        return (daily.groupby(["month", "city"])["value"].mean()
                .unstack("city").sort_index())

    def city_season_exceed(self, city, metric, season=None):
        """某城市（可按季节）超标天数，并给出逐月分布。"""
        from core import gb3095
        period = gb3095.choose_period(metric, "8h" if metric == "o3" else "24h")
        agg = "max8h" if period == "8h" else "mean"
        daily = self.daily_values(metric, agg)
        daily = daily[daily["city"] == city].copy()
        if daily.empty:
            raise ValueError(f"数据中没有城市：{city}")
        if season:
            months = config.SEASONS[season]
            month_num = daily["date"].str.slice(5, 7).astype(int)
            daily = daily[month_num.isin(months)]
        limit = gb3095.limit_of(metric, period)
        daily["exceeded"] = daily["value"] > limit + 1e-9
        daily["month"] = daily["date"].str.slice(5, 7)
        monthly = (daily.groupby("month")
                   .agg(days=("exceeded", "size"),
                        exceed_days=("exceeded", "sum"),
                        mean_value=("value", "mean"))
                   .reset_index())
        return {
            "city": city, "metric": metric, "period": period,
            "season": season, "limit": limit,
            "total_days": int(len(daily)),
            "exceed_days": int(daily["exceeded"].sum()),
            "mean_value": float(daily["value"].mean()) if len(daily) else None,
            "monthly": monthly.to_dict("records"),
        }

    def province_exceed(self, metric, period="24h"):
        """各省份超标城市-天数、占全国超标天数比例、省内超标率。"""
        from core import gb3095
        agg = "max8h" if period == "8h" else "mean"
        daily = self.daily_values(metric, agg)
        limit = gb3095.limit_of(metric, period)
        if limit is None:
            raise ValueError(f"{metric} 不支持 {period} 口径")
        daily = daily.assign(exceeded=daily["value"] > limit + 1e-9)
        grouped = (daily.groupby("province")
                   .agg(total_days=("exceeded", "size"),
                        exceed_days=("exceeded", "sum"),
                        cities=("city", "nunique"))
                   .reset_index())
        total = int(grouped["exceed_days"].sum())
        grouped["share"] = (grouped["exceed_days"] / total if total else 0.0)
        grouped["exceed_rate"] = grouped["exceed_days"] / grouped["total_days"]
        grouped = grouped[grouped["exceed_days"] > 0]
        grouped = grouped.sort_values("exceed_days", ascending=False)
        return {
            "metric": metric, "period": period, "limit": limit,
            "total_exceed_days": total,
            "total_city_days": int(len(daily)),
            "rows": grouped.reset_index(drop=True).to_dict("records"),
        }

    def detect_jumps(self, city, metric):
        """月度环比突变检测：|变化率| ≥ 阈值 且 |绝对变化| ≥ 阈值 才告警。"""
        daily = self.daily_values(metric, "mean")
        daily = daily[daily["city"] == city].copy()
        if daily.empty:
            raise ValueError(f"数据中没有城市：{city}")
        daily["month"] = daily["date"].str.slice(0, 7)
        monthly = daily.groupby("month")["value"].mean().sort_index()
        jumps = []
        values = monthly.tolist()
        months = monthly.index.tolist()
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            pct = diff / values[i - 1] if values[i - 1] else 0
            if abs(pct) >= config.ALERT_MOM_CHANGE and abs(diff) >= config.ALERT_MIN_DIFF:
                jumps.append({
                    "from": months[i - 1], "to": months[i],
                    "prev": round(float(values[i - 1]), 2),
                    "curr": round(float(values[i]), 2),
                    "change_pct": round(float(pct) * 100, 1),
                })
        return {"city": city, "metric": metric,
                "monthly": {m: round(float(v), 2) for m, v in monthly.items()},
                "jumps": jumps}


