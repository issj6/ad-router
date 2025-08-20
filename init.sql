-- 初始化数据库脚本
-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS ad_router DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_general_ci;

-- 使用数据库
USE ad_router;

-- 创建 request_log 表（SQLAlchemy 会自动创建，这里作为备用）
CREATE TABLE IF NOT EXISTS request_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rid VARCHAR(36) NOT NULL UNIQUE,
    ds_id VARCHAR(64) NOT NULL,
    up_id VARCHAR(64) NULL,
    event_type VARCHAR(16) NOT NULL,
    ad_id VARCHAR(128) NULL,
    click_id VARCHAR(128) NULL,
    ts BIGINT NOT NULL,
    os VARCHAR(16) NULL,
    upload_params JSON NULL,
    callback_params JSON NULL,
    upstream_url VARCHAR(2048) NULL,
    downstream_url VARCHAR(2048) NULL,
    track_time VARCHAR(32) NULL,
    is_callback_sent INT DEFAULT 0,
    callback_time VARCHAR(32) NULL,
    callback_event_type VARCHAR(64) NULL,
    
    INDEX idx_rid (rid),
    INDEX idx_ds_id (ds_id),
    INDEX idx_up_id (up_id),
    INDEX idx_ad_id (ad_id),
    INDEX idx_click_id (click_id),
    INDEX idx_req_ds_ad (ds_id, ad_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
