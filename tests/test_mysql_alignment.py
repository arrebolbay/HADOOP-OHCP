# -*- coding: utf-8 -*-
"""tests/test_mysql_alignment.py —— 跨引擎对账（MySQL 未就绪时自动跳过）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import mysql_query
from core.data_store import DataStore


def mysql_ready():
    try:
        rows = mysql_query(
            "SELECT city, annual_mean FROM fact_city_year "
            "WHERE metric='pm25' AND year=%s ORDER BY annual_mean DESC LIMIT 1",
            (config.DATASET_YEAR,), database=config.MYSQL_DB)
        return bool(rows)
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(mysql_ready(), "MySQL 结果表未就绪，跳过跨引擎对账")
class MySQLAlignmentTest(unittest.TestCase):
    def test_top_city_matches_local(self):
        row = mysql_query(
            "SELECT city, annual_mean FROM fact_city_year "
            "WHERE metric='pm25' AND year=%s ORDER BY annual_mean DESC LIMIT 1",
            (config.DATASET_YEAR,), database=config.MYSQL_DB)[0]
        local = DataStore().annual_mean("pm25", top_n=1).to_dict("records")[0]
        self.assertEqual(row["city"], local["city"])
        diff = abs(float(row["annual_mean"]) - float(local["value"])) / float(local["value"])
        self.assertLessEqual(diff, config.VALIDATE_MAX_REL_DIFF)


if __name__ == "__main__":
    unittest.main()
