# =============================================================================
# EdgeSentry - Ingestion Service (FastAPI + MQTT subscriber)
# =============================================================================
# This is the heart of the backend. It does two things at once:
#
#   1. Runs an MQTT subscriber (background thread) that receives readings from
#      the broker, validates them against the data contract, and stores them.
#   2. Serves a small HTTP API (health checks + query endpoints) via FastAPI.
#
# The MQTT side is where data flows in; the HTTP side is how you (and later,
# Kubernetes and Grafana) inspect the service.
#
# Data path:  broker --> on_message --> validate (Pydantic) --> storage (Postgres)
# =============================================================================

import json
import logging
from contextlib import asynccontextmanager

import paho.mqtt.client as mqtt
from fastapi import FastAPI
from pydantic import ValidationError

from app.config import settings
from app.models import DeviceHealth, SensorReading
from app import storage

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("edgesentry.ingestion")


# ---------------------------------------------------------------------------
# MQTT subscriber
# ---------------------------------------------------------------------------
# paho runs its network loop on a background thread (loop_start), so the
# subscriber and the FastAPI server coexist in one process without blocking
# each other.

def on_connect(client, userdata, flags, rc):
    """Called when the broker connection is established. We (re)subscribe here
    rather than once at startup, so a reconnect automatically re-subscribes."""
    if rc == 0:
        log.info("connected to MQTT broker at %s:%s",
                 settings.mqtt_host, settings.mqtt_port)
        client.subscribe(settings.topic_events)
        client.subscribe(settings.topic_readings)
        client.subscribe(settings.topic_health)
    else:
        log.error("MQTT connect failed with code %s", rc)


def on_message(client, userdata, msg):
    """Called for every message on a subscribed topic.

    This is the validation boundary: raw bytes come in, and only well-formed,
    contract-satisfying data proceeds to storage. Anything malformed is logged
    and dropped -- one bad message must never crash the subscriber.
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning("dropping unparseable message on %s: %s", msg.topic, e)
        return

    if msg.topic == settings.topic_health or "error" in payload:
        _handle_health(payload)
    else:
        _handle_reading(payload)


def _handle_reading(payload: dict):
    """Validate and store a sensor reading."""
    try:
        reading = SensorReading(**payload)   # <-- contract enforced here
    except ValidationError as e:
        log.warning("invalid reading dropped: %s", e.errors())
        return

    try:
        reading_id = storage.insert_reading(reading)
    except Exception as e:
        log.error("failed to store reading: %s", e)
        return

    log.info("stored reading id=%s device=%s temp=%.1f hum=%.1f significant=%s",
             reading_id, reading.device_id, reading.temp_c,
             reading.humidity_pct, reading.significant)

    # HOOK: a significant reading is where the LLM summarizer will be triggered
    # in a later step. For now we just note it.
    if reading.significant and settings.summarize_significant_only:
        log.debug("significant event id=%s -- LLM summary TODO", reading_id)


def _handle_health(payload: dict):
    """Validate and store a device health/fault message."""
    try:
        health = DeviceHealth(**payload)
    except ValidationError as e:
        log.warning("invalid health message dropped: %s", e.errors())
        return

    try:
        storage.insert_health(health)
        log.info("stored health device=%s error=%s",
                 health.device_id, health.error)
    except Exception as e:
        log.error("failed to store health: %s", e)


def start_mqtt() -> mqtt.Client:
    """Create, connect, and start the MQTT client on its background thread."""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.loop_start()   # background network thread
    return client


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
# The lifespan context starts the MQTT subscriber when the API boots and
# cleanly stops it on shutdown.

_mqtt_client: mqtt.Client | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mqtt_client
    log.info("starting EdgeSentry ingestion service")
    _mqtt_client = start_mqtt()
    yield
    log.info("shutting down")
    if _mqtt_client is not None:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()


app = FastAPI(title="EdgeSentry Ingestion", lifespan=lifespan)


@app.get("/health")
def health():
    """Liveness + readiness probe. Kubernetes will call this later.
    Reports the DB connection status so an unhealthy DB surfaces here."""
    db_ok = storage.health_check()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
    }


@app.get("/readings/{device_id}")
def get_readings(device_id: str, limit: int = 20):
    """Return the most recent readings for a device (for debugging / the UI)."""
    return {"device_id": device_id,
            "readings": storage.recent_readings(device_id, limit)}