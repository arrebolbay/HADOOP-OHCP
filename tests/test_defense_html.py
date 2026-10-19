# -*- coding: utf-8 -*-
"""tests/test_defense_html.py —— 答辩 HTML 材料自检（离线可用、页数与关键内容）。"""

import os
import re
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DECK = PROJECT / "docs" / "答辩演示.html"


class DefenseHTMLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DECK.read_text(encoding="utf-8")

    def test_slide_count(self):
        self.assertEqual(len(re.findall(r'<section class="slide', self.html)), 7)

    def test_no_external_resources(self):
        # 现场可能没有网络：答辩页不得依赖任何外链 CDN / 字体 / 图片
        external = re.findall(r'(?:src|href)="https?://[^"]+"', self.html)
        self.assertEqual(external, [])

    def test_key_sections_present(self):
        for keyword in ("技术栈", "优点", "局限与应对", "三方对账", "3.5 分钟录屏路线"):
            self.assertIn(keyword, self.html)

    def test_start_scripts_exist(self):
        for name in ("start.sh", "start.bat"):
            self.assertTrue((PROJECT / name).exists(), name)
        self.assertTrue(os.access(PROJECT / "start.sh", os.X_OK),
                        "start.sh 需要可执行权限（chmod +x start.sh）")


if __name__ == "__main__":
    unittest.main()
