-- SQLite twin of ../0007_monitor_detail.sql.

ALTER TABLE monitor_seen ADD COLUMN known_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE monitor_seen ADD COLUMN rejected_count INTEGER NOT NULL DEFAULT 0;

UPDATE monitor_seen SET
    known_count = (SELECT COUNT(*) FROM monitor_stars s, json_each(s.record, '$.detections') d
                   WHERE s.run_id = monitor_seen.run_id AND s.tic = monitor_seen.tic
                   AND json_type(s.record, '$.detections') = 'array'
                   AND CASE WHEN d.type = 'object' THEN json_extract(d.value, '$.outcome') END
                       = 'known'),
    rejected_count = (SELECT COUNT(*) FROM monitor_stars s, json_each(s.record, '$.detections') d
                      WHERE s.run_id = monitor_seen.run_id AND s.tic = monitor_seen.tic
                      AND json_type(s.record, '$.detections') = 'array'
                      AND CASE WHEN d.type = 'object' THEN json_extract(d.value, '$.outcome') END
                       = 'rejected');

CREATE INDEX monitor_stars_tic ON monitor_stars (tic, searched_at DESC);
