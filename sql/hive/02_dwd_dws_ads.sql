-- =============================================================================
-- sql/hive/02_dwd_dws_ads.sql —— DWD 清洗 -> DWS 汇总 -> ADS 应用层
-- =============================================================================
-- 口径与 Python 侧保持一致：
--   * 物理量程过滤（PM2.5 0~1000、PM10 0~1500 ...）
--   * 城市日均值要求至少 12 个有效小时
--   * 年均 = 日均值的算术平均（先日均、再年均）
--   * GB 3095-2012 二级标准：PM2.5 年均 35、24h 75 μg/m³
-- =============================================================================
USE air_quality;

-- 单机/教学环境优化：小数据量走本地模式，避免为每个 CTAS 启动 YARN 容器
SET hive.exec.mode.local.auto=true;
SET hive.exec.mode.local.auto.inputbytes.max=1073741824;
SET hive.exec.mode.local.auto.input.files.max=32;
SET mapreduce.job.reduces=1;
SET mapreduce.task.io.sort.mb=64;
SET mapreduce.map.memory.mb=1024;
SET mapreduce.reduce.memory.mb=1024;
SET hive.stats.autogather=false;

-- ------------------------- DWD：清洗后的明细层 -------------------------
DROP TABLE IF EXISTS dwd_air_quality;
CREATE TABLE dwd_air_quality AS
SELECT
    city, province, dt, CAST(hour AS INT) AS hour,
    CAST(pm25 AS DOUBLE) AS pm25, CAST(pm10 AS DOUBLE) AS pm10,
    CAST(so2 AS DOUBLE) AS so2, CAST(no2 AS DOUBLE) AS no2,
    CAST(o3 AS DOUBLE) AS o3, CAST(co AS DOUBLE) AS co,
    CAST(aqi AS DOUBLE) AS aqi,
    CASE
        WHEN CAST(aqi AS DOUBLE) <= 50 THEN '优'
        WHEN CAST(aqi AS DOUBLE) <= 100 THEN '良'
        WHEN CAST(aqi AS DOUBLE) <= 150 THEN '轻度污染'
        WHEN CAST(aqi AS DOUBLE) <= 200 THEN '中度污染'
        WHEN CAST(aqi AS DOUBLE) <= 300 THEN '重度污染'
        ELSE '严重污染'
    END AS quality
FROM ods_air_quality
WHERE city IS NOT NULL AND city <> ''
  AND dt RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  AND CAST(hour AS INT) BETWEEN 0 AND 23
  AND CAST(pm25 AS DOUBLE) BETWEEN 0 AND 1000
  AND CAST(pm10 AS DOUBLE) BETWEEN 0 AND 1500
  AND CAST(so2 AS DOUBLE) BETWEEN 0 AND 2000
  AND CAST(no2 AS DOUBLE) BETWEEN 0 AND 1000
  AND CAST(co AS DOUBLE) BETWEEN 0 AND 50
  AND CAST(o3 AS DOUBLE) BETWEEN 0 AND 1000;

-- ------------------------- DWD：城市日均 -------------------------
DROP TABLE IF EXISTS dwd_city_daily;
CREATE TABLE dwd_city_daily AS
SELECT city, province, dt,
       AVG(pm25) AS pm25, COUNT(pm25) AS n_pm25,
       AVG(pm10) AS pm10, AVG(so2) AS so2, AVG(no2) AS no2,
       AVG(co) AS co, AVG(o3) AS o3, AVG(aqi) AS aqi
FROM dwd_air_quality
GROUP BY city, province, dt
HAVING COUNT(pm25) >= 12;

-- ------------------------- DWS：城市-年 / 城市-月 -------------------------
DROP TABLE IF EXISTS dws_city_year;
CREATE TABLE dws_city_year AS
SELECT city, province, SUBSTR(dt, 1, 4) AS year,
       AVG(pm25) AS annual_pm25, AVG(pm10) AS annual_pm10,
       AVG(so2) AS annual_so2, AVG(no2) AS annual_no2,
       AVG(o3) AS annual_o3, COUNT(*) AS days
FROM dwd_city_daily
GROUP BY city, province, SUBSTR(dt, 1, 4);

DROP TABLE IF EXISTS dws_city_month;
CREATE TABLE dws_city_month AS
SELECT city, province, SUBSTR(dt, 1, 7) AS month,
       AVG(pm25) AS pm25, AVG(o3) AS o3, COUNT(*) AS days
FROM dwd_city_daily
GROUP BY city, province, SUBSTR(dt, 1, 7);

-- ------------------------- ADS：应用结果层 -------------------------
DROP TABLE IF EXISTS ads_city_year_pm25;
CREATE TABLE ads_city_year_pm25 AS
SELECT city, province, year, ROUND(annual_pm25, 2) AS annual_mean, days,
       CASE WHEN annual_pm25 > 35 THEN 1 ELSE 0 END AS exceeded
FROM dws_city_year
WHERE year = '2024';

DROP TABLE IF EXISTS ads_top_city_pm25;
CREATE TABLE ads_top_city_pm25 AS
SELECT * FROM ads_city_year_pm25 ORDER BY annual_mean DESC LIMIT 20;

DROP TABLE IF EXISTS ads_province_exceed_pm25;
CREATE TABLE ads_province_exceed_pm25 AS
SELECT province,
       SUM(CASE WHEN pm25 > 75 THEN 1 ELSE 0 END) AS exceed_days,
       COUNT(*) AS total_days,
       ROUND(SUM(CASE WHEN pm25 > 75 THEN 1 ELSE 0 END) / COUNT(*), 4) AS exceed_rate
FROM dwd_city_daily
WHERE SUBSTR(dt, 1, 4) = '2024'
GROUP BY province;

-- 与 MapReduce 对账专用：逐小时算术平均（MR 的单阶段口径）
DROP TABLE IF EXISTS ads_city_pm25_hourly;
CREATE TABLE ads_city_pm25_hourly AS
SELECT city, ROUND(AVG(pm25), 2) AS hourly_mean, COUNT(*) AS n
FROM dwd_air_quality
GROUP BY city;

-- 验收查询
SELECT * FROM ads_top_city_pm25 LIMIT 5;
SELECT COUNT(*) AS dwd_rows FROM dwd_air_quality;
SELECT COUNT(*) AS ads_city_rows FROM ads_city_pm25_hourly;

