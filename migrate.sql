-- 数据库迁移脚本：更新时间字段结构
-- 执行前请备份数据库

USE ad_router;
-- 0. 如需新增 channel_id 字段
ALTER TABLE request_log ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NULL;
CREATE INDEX IF NOT EXISTS idx_channel_id ON request_log (channel_id);


-- 1. 添加新的时间字段
ALTER TABLE request_log ADD COLUMN track_time VARCHAR(32) NULL COMMENT 'track创建时间（上海时区）';
ALTER TABLE request_log ADD COLUMN callback_time_new VARCHAR(32) NULL COMMENT '回调时间（上海时区）';

-- 2. 将现有的 callback_time (BIGINT) 转换为格式化时间并存入新字段
UPDATE request_log
SET callback_time_new = DATE_FORMAT(
    CONVERT_TZ(
        FROM_UNIXTIME(callback_time / 1000),
        '+00:00',
        '+08:00'
    ),
    '%Y-%m-%d %H:%i:%s'
)
WHERE callback_time IS NOT NULL;

-- 3. 根据 ts 字段生成 track_time（假设 ts 是毫秒时间戳）
UPDATE request_log
SET track_time = DATE_FORMAT(
    CONVERT_TZ(
        FROM_UNIXTIME(ts / 1000),
        '+00:00',
        '+08:00'
    ),
    '%Y-%m-%d %H:%i:%s'
)
WHERE ts IS NOT NULL;

-- 4. 删除旧的 callback_time 字段
ALTER TABLE request_log DROP COLUMN callback_time;

-- 5. 将新字段重命名为 callback_time
ALTER TABLE request_log CHANGE COLUMN callback_time_new callback_time VARCHAR(32) NULL COMMENT '回调时间（上海时区）';

-- 6. 验证迁移结果
SELECT
    rid,
    ds_id,
    event_type,
    ts,
    track_time,
    callback_time,
    is_callback_sent
FROM request_log
LIMIT 5;
