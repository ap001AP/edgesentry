-- ============================================================================
-- EdgeSentry - Database schema
-- ============================================================================
-- Mirrors the SensorReading data contract in app/models.py. If you change one,
-- change the other -- they are two views of the same contract (one for the
-- wire, one for storage).
--
-- Apply with:
--   docker exec -i edgesentry-db psql -U edgesentry -d edgesentry < db/schema.sql
-- ============================================================================

-- --- Readings -------------------------------------------------------------
-- Every reading the device produces, routine or significant. This is the raw
-- time-series that drift detection samples and dashboards query.
CREATE TABLE IF NOT EXISTS readings (
    id            BIGSERIAL PRIMARY KEY,   -- auto-incrementing surrogate key

    device_id     TEXT        NOT NULL,
    device_ts     DOUBLE PRECISION NOT NULL,  -- device clock (not real time!)
    received_at   TIMESTAMPTZ NOT NULL,       -- host wall-clock, authoritative

    temp_c        REAL        NOT NULL,
    humidity_pct  REAL        NOT NULL,

    significant   BOOLEAN     NOT NULL,       -- edge pre-filter verdict
    reason        TEXT        NOT NULL,       -- why it was flagged
    fw            TEXT        NOT NULL        -- firmware version
);

-- Query patterns we expect:
--   * "recent readings for device X"      -> (device_id, received_at)
--   * "recent significant events"         -> (significant, received_at)
-- Indexes make those fast as the table grows.
CREATE INDEX IF NOT EXISTS idx_readings_device_time
    ON readings (device_id, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_readings_significant_time
    ON readings (significant, received_at DESC)
    WHERE significant;   -- partial index: only rows we actually filter on


-- --- Device health --------------------------------------------------------
-- Sensor faults and (future) device telemetry from the edgesentry/health topic.
CREATE TABLE IF NOT EXISTS device_health (
    id           BIGSERIAL PRIMARY KEY,
    device_id    TEXT        NOT NULL,
    device_ts    DOUBLE PRECISION NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL,
    error        TEXT,
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_health_device_time
    ON device_health (device_id, received_at DESC);


-- --- Incident summaries ---------------------------------------------------
-- The LLM's output for significant events (populated in a later step).
-- Linked back to the reading that triggered it so you can trace a summary
-- to its source data -- important for debugging and for observability.
CREATE TABLE IF NOT EXISTS incidents (
    id            BIGSERIAL PRIMARY KEY,
    reading_id    BIGINT      REFERENCES readings(id) ON DELETE CASCADE,

    device_id     TEXT        NOT NULL,
    summary       TEXT        NOT NULL,      -- plain-English description
    likely_cause  TEXT        NOT NULL,
    severity      TEXT        NOT NULL,      -- info | warning | critical

    model         TEXT,                      -- which LLM produced this
    latency_ms    INTEGER,                   -- how long inference took
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_time
    ON incidents (created_at DESC);