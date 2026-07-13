# =============================================================================
# EdgeSentry - Data Contract (Pydantic models)
# =============================================================================
# These models ARE the contract between the device and the backend. The Pico's
# firmware (build_payload) and the simulator both emit JSON that must satisfy
# SensorReading. If a message doesn't fit, validation fails loudly here rather
# than causing a mysterious bug three layers deeper.
#

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

class Reason(str, Enum):
    """Why the edge pre-filter did (or didn't) flag a reading.

    Mirrors the reasons produced by the firmware's is_significant().
    Using an Enum means an unexpected reason value
    is caught at validation time, and downstream code can switch on known cases.
    """
    
    FIRST_READING = "first_reading"
    ROUTINE = "routine"
    TEMP_DELTA = "temp_delta"
    HUMIDITY_DELTA = "humidity_delta"
    TEMP_OUT_OF_RANGE = "temp_out_of_range"
    HUMIDITY_OUT_OF_RANGE = "humidity_out_of_range"

class SensorReading(BaseModel):
    """One reading as emitted by the device and enriched by the bridge.

    Field constraints double as validation: temp/humidity must be within
    physically sane bounds, so a corrupted message can't poison storage.
    """

    device_id: str = Field(..., description="Stable per-device identifier")
    ts: float = Field(..., description="Device-side timestamp (device clock)")
    temp_c: float = Field(..., ge=-40.0, le=80.0, description="Temperature in Celsius (DHT22 range)")
    humidity_pct: float = Field(..., ge=0.0, le=100.0, description="Relative humidity percentage")
    significant: bool = Field(..., description="Edge pre-filter verdict")
    reason: Reason = Field(..., description="Why it was (or wasn't) flagged")
    fw: str = Field(..., description="Firmware version string")

    # The host stamps authoritative wall-clock time here; the device 'ts' is
    # device-relative and not reliable as real time.
    received_at: Optional[float] = Field(None, description="Host-side wall-clock receive time (epoch seconds)")

    # Reject unknown fields outright. If the device starts sending a new key,
    # we want to notice and update the contract deliberately
    model_config = {
        "extra": "forbid",
    }

class DeviceHealth(BaseModel):
    """Device telemetry / fault messages (the edgesentry/health topic).

    The firmware emits an error line on sensor faults; a future Pico W would
    also send RSSI, free memory, uptime, etc. Kept permissive because health
    payloads vary more than readings.
    """

    device_id: str
    ts: float
    error: Optional[str] = None
    detail: Optional[str] = None
    received_at: Optional[float] = None

class IncidentSummary(BaseModel):
    """The LLM's output for a significant event (populated in a later step).

    Defined here now so the contract for the LLM layer is visible up front.
    The guardrails will validate the LLM's response against this shape.
    """

    device_id: str
    summary: str = Field(..., description="LLM-generated summary of the incident")
    likely_cause: str = Field(..., description="LLM-generated likely cause of the incident")
    severity: str = Field(..., description="One of: info, warning, critical")
    reading_ts: float = Field(..., description="Timestamp of the reading that triggered the incident")





