# =============================================================================
# EdgeSentry - Storage layer
# =============================================================================
# Everything that touches the database lives here. The rest of the app calls
# these functions and never writes SQL itself.
# =============================================================================

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.models import DeviceHealth, SensorReading

log = logging.getLogger(__name__)


# A single connection pool for the process. SQLAlchemy manages the pool; we
# don't open/close a connection per message (that would be slow and would
# exhaust the DB under load).
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Lazily create the shared engine (connection pool)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=5,          # keep a small pool; this is a single service
            max_overflow=5,
            pool_pre_ping=True,   # check a connection is alive before using it
                                  # (guards against stale conns after a DB restart)
        )
    return _engine


def _to_utc(epoch_seconds: Optional[float]) -> datetime:
    """Convert a host epoch timestamp to a timezone-aware UTC datetime.

    If the bridge didn't stamp received_at (shouldn't happen, but be safe),
    fall back to 'now' -- we'd rather store the row with an approximate time
    than drop it.
    """
    if epoch_seconds is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)


def insert_reading(reading: SensorReading) -> int:
    """Insert one sensor reading. Returns the new row's id.

    The id is returned because a significant reading may trigger an LLM
    incident, and that incident needs to reference the reading it came from
    (the foreign key in the incidents table).
    """
    sql = text("""
        INSERT INTO readings
            (device_id, device_ts, received_at,
             temp_c, humidity_pct, significant, reason, fw)
        VALUES
            (:device_id, :device_ts, :received_at,
             :temp_c, :humidity_pct, :significant, :reason, :fw)
        RETURNING id
    """)

    params = {
        "device_id": reading.device_id,
        "device_ts": reading.ts,
        "received_at": _to_utc(reading.received_at),
        "temp_c": reading.temp_c,
        "humidity_pct": reading.humidity_pct,
        "significant": reading.significant,
        # .value because reason is an Enum; the DB stores the plain string.
        "reason": reading.reason.value,
        "fw": reading.fw,
    }

    with get_engine().begin() as conn:   # begin() = transaction, auto-commits
        row = conn.execute(sql, params).one()
        return row.id


def insert_health(health: DeviceHealth) -> int:
    """Insert a device health/fault message. Returns the new row's id."""
    sql = text("""
        INSERT INTO device_health
            (device_id, device_ts, received_at, error, detail)
        VALUES
            (:device_id, :device_ts, :received_at, :error, :detail)
        RETURNING id
    """)

    params = {
        "device_id": health.device_id,
        "device_ts": health.ts,
        "received_at": _to_utc(health.received_at),
        "error": health.error,
        "detail": health.detail,
    }

    with get_engine().begin() as conn:
        row = conn.execute(sql, params).one()
        return row.id


def recent_readings(device_id: str, limit: int = 20) -> list[dict]:
    """Fetch the most recent readings for a device, newest first.

    Used to give the LLM context ("what was normal before this spike?") and
    to serve the API's query endpoint. The index on (device_id, received_at)
    makes this fast.
    """
    sql = text("""
        SELECT id, device_id, device_ts, received_at,
               temp_c, humidity_pct, significant, reason, fw
        FROM readings
        WHERE device_id = :device_id
        ORDER BY received_at DESC
        LIMIT :limit
    """)

    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"device_id": device_id, "limit": limit})
        # ._mapping turns each Row into a dict-like view.
        return [dict(r._mapping) for r in rows]


def health_check() -> bool:
    """Cheap liveness probe for the DB. Used by the API's /health endpoint
    and (later) by Kubernetes readiness probes."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.warning("database health check failed: %s", e)
        return False