# =============================================================================
# EdgeSentry - Pico Firmware (MicroPython) - USB SERIAL VERSION
# =============================================================================
# Runs on a plain Raspberry Pi Pico (no wifi). Reads a DHT22 temperature/
# humidity sensor, applies a lightweight on-device pre-filter (the "edge" part
# of the project), and prints each reading as a line of JSON to USB serial.
#
# A host-side bridge script (bridge/serial_to_mqtt.py) reads these lines over
# the USB cable and republishes them to MQTT. The Pico itself knows nothing
# about MQTT or the network -- it just produces data. (See ADR 0001.)
#
# HOW TO RUN:
#   1. Flash MicroPython onto the Pico (drag the .uf2, or use Thonny).
#   2. Wire DHT22:  VCC->3V3 (pin36), GND->GND (pin38), DATA->GP15 (pin20).
#   3. Save this file onto the Pico as main.py (it auto-runs on boot).
#   4. Optionally copy config.py (from config_example.py) to tune settings.
# =============================================================================

import time 
import json
import machine
import dht 

# Settings are kept in a separate config module so they can be tuned without editing logic. 
# If config.py isn't present on the device, fall back to sensible defaults.
try:
    import config
    DATA_PIN = config.DATA_PIN
    READ_INTERVAL_S = config.READ_INTERVAL_S
    TEMP_DELTA_C = config.TEMP_DELTA_C
    HUMIDITY_DELTA_PCT = config.HUMIDITY_DELTA_PCT
    TEMP_RANGE = config.TEMP_RANGE
    HUMIDITY_RANGE = config.HUMIDITY_RANGE
except ImportError:
    DATA_PIN = 15                # GP15 == physical pin 20
    READ_INTERVAL_S = 5          # DHT22 needs >=2s between reads
    TEMP_DELTA_C = 0.5           # flag if temp moved this much since last flagged
    HUMIDITY_DELTA_PCT = 2.0     # flag if humidity moved this much
    TEMP_RANGE = (-10, 50)       # always-flag if outside this band
    HUMIDITY_RANGE = (0, 100)

SENSOR = dht.DHT22(machine.Pin(DATA_PIN))
LED = machine.Pin("LED", machine.Pin.OUT)

DEVICE_ID = "pico-" + machine.unique_id().hex()

# ---- Edge pre-filter state --------------------------------------------------
# Remembers the last reading we flagged as significant, so we can measure change.
_last_sent = {"temp": None, "humidity": None}

def is_significant(temp, humidity):
    """Edge anomaly pre-filter.
 
    Returns (significant: bool, reason: str). 'significant' readings are worth
    the cloud LLM's attention; everything else is still emitted but tagged
    'routine' so the backend can downsample it cheaply.
    """
    # Always flag values outside the physically expected band (real anomaly or a sensor fault ).  
    if not (TEMP_RANGE[0] <= temp <= TEMP_RANGE[1]):
        return True, "temp_out_of_range"
    if not (HUMIDITY_RANGE[0] <= humidity <= HUMIDITY_RANGE[1]):
        return True, "humidity_out_of_range"
    
    # The first reading after boot has no baseline to compare against.
    if _last_sent["temp"] is None:
        return True, "first_reading"
    
    # Flag meaningful movement since the last flagged reading.
    if abs(temp - _last_sent["temp"]) >= TEMP_DELTA_C:
        return True, "temp_delta"
    if abs(humidity - _last_sent["humidity"]) >= HUMIDITY_DELTA_PCT:
        return True, "humidity_delta"
    
    return False, "routine"

def read_sensor():
    """Read the DHT22. Returns (temp_c, humidity_pct). Raises OSError on fault."""
    SENSOR.measure() # triggers a fresh reading 
    return SENSOR.temperature(), SENSOR.humidity()

def build_payload(temp, humidity, significant, reason):
    """Assemble the message. This dict shape IS the data contract -- the
    simulator and the backend's Pydantic model must match it exactly."""
    return {
        "device_id": DEVICE_ID,
        "ts": time.time(), # device clock (seconds)
        "temp_c": round(temp, 2),
        "humidity_pct": round(humidity, 2),
        "significant": significant, # edge pre-filter verdict 
        "reason": reason, # why it was (or wasn"t) flagged 
        "fw": "edgesentry-serial-1.0",
    }

def emit(payload):
    """Send one reading to the host as a single line of JSON over USB serial.
 
    print() in MicroPython writes to the USB serial console, so the host-side
    bridge just reads stdin/serial line by line. One JSON object per line
    (newline-delimited JSON) makes parsing on the other end trivial and robust.
    """
    print(json.dumps(payload))

def main():
    for _ in range(3):
        LED.on(); time.sleep(0.1); LED.off(); time.sleep(0.1)
    
    while True:
        try:
            temp, humidity = read_sensor()
            significant, reason = is_significant(temp, humidity)
            emit(build_payload(temp, humidity, significant, reason))

            if significant:
                _last_sent["temp"] = temp
                _last_sent["humidity"] = humidity
            
            LED.on(); time.sleep(0.05); LED.off() # quick blink confirms a successful read/emit cycle

        except OSError as e:
            # DHT22 reads fail intermittently (timing-sensitive protocol).
            # Emit a structured error line so the host can log it, then carry on.
            print(json.dumps({
                "device_id": DEVICE_ID,
                "ts": time.time(),
                "error": "sensor_read_failed",
                "details": str(e),
            }))
            LED.on(); time.sleep(0.5); LED.off() # longer blink = fault 
        
        time.sleep(READ_INTERVAL_S)

if __name__ == "__main__":
    main()
