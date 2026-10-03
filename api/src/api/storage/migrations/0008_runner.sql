-- The search server's latest heartbeat (POST /monitor/heartbeat): its state, next run and the
-- ledger's per-queue counts, for GET /monitor/now's `runner` block and GET /monitor/coverage/queues.
-- One row.
CREATE TABLE monitor_heartbeat (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
