# 天池数据集放置说明（可选）

把从阿里云天池下载并解压的 CSV 放在本目录（`data/raw/tianchi/`），
然后**移走 `data/raw/daily/` 下的日文件**（或改 config 指向），
再运行：

```bash
python3 steps/step02_prepare_data.py
```

`step02` 会自动识别本目录并规范化为标准长表：

| 天池字段 | 标准字段 | 说明 |
| --- | --- | --- |
| 城市 / city | city | 必填 |
| 省份 / province | province | 可选，缺失时用行政区划表补齐 |
| 日期 / date | date | 必填，支持 `YYYY-MM-DD` / `YYYYMMDD` |
| 时间 / hour | hour | 可选，默认 0 |
| PM2.5 / PM10 / SO2 / NO2 / CO / O3 / AQI | 同名小写 | 数值列 |
| 质量等级 / quality | quality | 可选，缺失时由 AQI 生成 |

要求：
- 必须是真实公开监测数据，禁止人工构造；
- 若为"监测点-小时"粒度，请先按城市+日期+小时聚合；字段不一致时
  调整 `steps/step02_prepare_data.py` 的 `load_tianchi_long()`；
- 本目录中的 CSV 不随项目提交（数据体积较大）。
