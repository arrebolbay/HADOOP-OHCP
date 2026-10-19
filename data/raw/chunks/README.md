# 按月分片目录（不入库）

`step02_prepare_data.py` 会把日文件转换成长表并按月写出
`air_quality_2024-MM.csv`（约 190MB，仓库不提交）。

重新生成：

```bash
python3 steps/step02_prepare_data.py
python3 steps/step03_explore_data.py
```
