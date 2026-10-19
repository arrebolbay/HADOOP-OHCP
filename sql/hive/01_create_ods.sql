-- =============================================================================
-- sql/hive/01_create_ods.sql —— Hive 数据库 + ODS 贴源层外部表
-- =============================================================================
-- ODS 层字段全部用 STRING：原始 CSV 里的空值/异常值原样保留，
-- 到 DWD 层再统一做类型转换与过滤（和 Python 清洗逻辑保持一致的口径）。
-- 数据位置：hdfs:///air_quality/ods/air_quality（由 step04 上传的分片 CSV）
-- =============================================================================
CREATE DATABASE IF NOT EXISTS air_quality;
USE air_quality;

SET hive.exec.mode.local.auto=true;
SET hive.exec.mode.local.auto.inputbytes.max=1073741824;
SET hive.exec.mode.local.auto.input.files.max=32;

DROP TABLE IF EXISTS ods_air_quality;
CREATE EXTERNAL TABLE ods_air_quality (
    city      STRING COMMENT '城市',
    province  STRING COMMENT '省份',
    dt        STRING COMMENT '日期 YYYY-MM-DD',
    hour      STRING COMMENT '小时 0-23',
    pm25      STRING COMMENT 'PM2.5 μg/m³',
    pm10      STRING COMMENT 'PM10 μg/m³',
    so2       STRING COMMENT 'SO₂ μg/m³',
    no2       STRING COMMENT 'NO₂ μg/m³',
    o3        STRING COMMENT 'O₃ μg/m³',
    co        STRING COMMENT 'CO mg/m³',
    aqi       STRING COMMENT 'AQI',
    quality   STRING COMMENT '质量等级'
)
COMMENT '全国城市空气质量小时监测（真实公开数据，按月分片 CSV）'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/air_quality/ods/air_quality'
TBLPROPERTIES ('skip.header.line.count' = '1');

-- 快速验证：行数与样例
SELECT COUNT(*) AS ods_rows FROM ods_air_quality;
SELECT * FROM ods_air_quality LIMIT 5;
