-- =============================================================================
-- sql/mysql/01_schema.sql —— MySQL 结果库（维表 + 事实表 + 视图 + 存储过程 + 事件）
-- =============================================================================
-- 角色：Hive/MapReduce 算完的 ADS 结果落到 MySQL，供 Agent 快速查询与前端展示。
-- 注意：MySQL 8.0 默认字符集用 utf8mb4，城市/省份中文名不会乱码。
-- =============================================================================
CREATE DATABASE IF NOT EXISTS air_quality DEFAULT CHARACTER SET utf8mb4;
USE air_quality;

DROP TABLE IF EXISTS fact_city_year;
CREATE TABLE fact_city_year (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    city        VARCHAR(64)  NOT NULL COMMENT '城市',
    province    VARCHAR(64)  NOT NULL COMMENT '省份',
    year        INT          NOT NULL COMMENT '年份',
    metric      VARCHAR(16)  NOT NULL COMMENT 'pm25/pm10/so2/no2/o3/co',
    annual_mean DECIMAL(10,2) NOT NULL COMMENT '年均浓度',
    days        INT          NOT NULL COMMENT '有效天数',
    exceeded    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否超过年均限值',
    PRIMARY KEY (id),
    UNIQUE KEY uk_city_metric_year (city, metric, year),
    KEY idx_metric_year_value (metric, year, annual_mean)
) ENGINE=InnoDB COMMENT='城市-年 指标结果表';

DROP TABLE IF EXISTS fact_city_month;
CREATE TABLE fact_city_month (
    id           BIGINT NOT NULL AUTO_INCREMENT,
    city         VARCHAR(64) NOT NULL,
    province     VARCHAR(64) NOT NULL,
    month        CHAR(7) NOT NULL COMMENT 'YYYY-MM',
    metric       VARCHAR(16) NOT NULL,
    monthly_mean DECIMAL(10,2) NOT NULL,
    days         INT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_city_month_metric (city, month, metric),
    KEY idx_month (month)
) ENGINE=InnoDB COMMENT='城市-月 趋势表';

DROP TABLE IF EXISTS fact_province_exceed;
CREATE TABLE fact_province_exceed (
    id          BIGINT NOT NULL AUTO_INCREMENT,
    province    VARCHAR(64) NOT NULL,
    year        INT NOT NULL,
    metric      VARCHAR(16) NOT NULL,
    period      VARCHAR(8) NOT NULL COMMENT '24h / 8h',
    exceed_days INT NOT NULL COMMENT '超标城市-天数',
    total_days  INT NOT NULL COMMENT '有效城市-天数',
    exceed_rate DECIMAL(6,4) NOT NULL,
    share       DECIMAL(6,4) NOT NULL COMMENT '占全国超标天数比例',
    PRIMARY KEY (id),
    UNIQUE KEY uk_province_metric (province, year, metric, period)
) ENGINE=InnoDB COMMENT='省份超标统计表';

DROP TABLE IF EXISTS dim_city;
CREATE TABLE dim_city (
    city     VARCHAR(64) NOT NULL,
    province VARCHAR(64) NOT NULL,
    PRIMARY KEY (city)
) ENGINE=InnoDB COMMENT='城市维度表';

-- ------------------------- 视图 -------------------------
CREATE OR REPLACE VIEW v_top_city_pm25 AS
SELECT city, province, annual_mean, days, exceeded
FROM fact_city_year
WHERE metric = 'pm25'
ORDER BY annual_mean DESC
LIMIT 20;

CREATE OR REPLACE VIEW v_province_exceed_rank AS
SELECT province, exceed_days, exceed_rate,
       RANK() OVER (ORDER BY exceed_days DESC) AS rk
FROM fact_province_exceed
WHERE metric = 'pm25' AND period = '24h';

-- ------------------------- 存储过程 -------------------------
DROP PROCEDURE IF EXISTS sp_top_cities;
DELIMITER $$
CREATE PROCEDURE sp_top_cities(IN p_metric VARCHAR(16), IN p_year INT, IN p_top INT)
BEGIN
    SELECT city, province, annual_mean, days, exceeded
    FROM fact_city_year
    WHERE metric = p_metric AND year = p_year
    ORDER BY annual_mean DESC
    LIMIT p_top;
END$$
DELIMITER ;

-- ------------------------- 定时事件（保持超标标记最新） -------------------------
DROP EVENT IF EXISTS ev_refresh_exceed;
CREATE EVENT ev_refresh_exceed
ON SCHEDULE EVERY 1 DAY
DO
    UPDATE fact_city_year
    SET exceeded = CASE WHEN metric = 'pm25' AND annual_mean > 35 THEN 1
                        WHEN metric = 'pm10' AND annual_mean > 70 THEN 1
                        WHEN metric = 'so2'  AND annual_mean > 60 THEN 1
                        WHEN metric = 'no2'  AND annual_mean > 40 THEN 1
                        ELSE 0 END;
