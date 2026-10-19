# 字体目录说明

仓库**不包含**中文字体文件（SimHei / 微软雅黑等为商业字体，避免版权问题）。

`config.font_path()` 会按以下顺序自动寻找可用字体：

1. `data/fonts/simhei.ttf`（推荐：自行放入一个有授权的中文字体）
2. 项目父目录 `data/fonts/simhei.ttf`
3. 系统 Noto CJK / 文泉驿等开源字体
4. Windows 字体目录（WSL 环境：`/mnt/c/Windows/Fonts/msyh.ttc`）

如果图表中文显示为方框，请把一个有授权的中文字体复制为：

```bash
mkdir -p data/fonts
cp /path/to/your/font.ttf data/fonts/simhei.ttf
```

再重新运行绘图步骤即可。
