# 字体目录说明

仓库包含 **文泉驿微米黑（WenQuanYi Micro Hei）** 作为默认可用的开源中文字体：

- 文件：`wqy-microhei.ttc`（约 5MB）
- 许可证：Apache-2.0 或 GPL-3+ with Font exception（见 `WQY-MicroHei-LICENSE.txt`）
- 代码会自动使用 `data/fonts/wqy-microhei.ttc`，无需额外配置

如需换成其他字体，可放入：

```bash
cp /path/to/your/font.ttf data/fonts/simhei.ttf
```

`config.font_path()` 的查找顺序：`simhei.ttf` → `wqy-microhei.ttc` → 系统 Noto/文泉驿 →
Windows 字体目录（WSL：`/mnt/c/Windows/Fonts/`）。

> 商业字体（SimHei、微软雅黑等）不随仓库分发，避免版权问题。
