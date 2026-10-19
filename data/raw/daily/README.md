# 原始日文件目录（不入库）

仓库不提交约 135MB 的原始日文件。首次使用请运行：

```bash
python3 scripts/download_real_data.py --start 2024-01-01 --end 2024-12-31 --workers 6
```

下载完成后，本目录会出现 `china_cities_YYYYMMDD.csv`（每天一个）。
也可以把天池数据集放到 `data/raw/tianchi/`（见其中 README）。

> 比赛现场不联网：请在赛前完成下载，现场直接读取本地文件。
