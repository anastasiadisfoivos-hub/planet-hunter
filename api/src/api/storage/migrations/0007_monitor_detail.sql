-- Monitor detail for the web's monitor page: GET /monitor/stats counts detections whose outcome
-- is "known" and "rejected" (over each star's latest search), and GET /monitor/stars/{tic}
-- finds a star's latest stored record by tic.

ALTER TABLE monitor_seen ADD COLUMN known_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE monitor_seen ADD COLUMN rejected_count INTEGER NOT NULL DEFAULT 0;

-- Backfill from the latest search's full record, where its run is still kept (older stars stay 0).
UPDATE monitor_seen m SET
    known_count = (SELECT COUNT(*) FROM jsonb_array_elements(s.record->'detections') d
                   WHERE d->>'outcome' = 'known'),
    rejected_count = (SELECT COUNT(*) FROM jsonb_array_elements(s.record->'detections') d
                      WHERE d->>'outcome' = 'rejected')
FROM monitor_stars s
WHERE s.run_id = m.run_id AND s.tic = m.tic AND jsonb_typeof(s.record->'detections') = 'array';

CREATE INDEX monitor_stars_tic ON monitor_stars (tic, searched_at DESC);
