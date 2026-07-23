#!/usr/bin/env python3
# =============================================================================
# EdgeSentry - Device Simulator
# =============================================================================
# Impersonates the Pico + bridge: generates readings that satisfy the SAME data
# contract and publishes them to the SAME MQTT topics. 
#
# WHY THIS EXISTS (three jobs):
#   1. Develop the backend without the Pico plugged in.
#   2. Serve as a CI fixture -- tests can run the pipeline with no hardware.
#   3. Load-test -- crank the rate up to see how the service behaves under load.
#
# It reproduces the firmware's edge pre-filter logic so the significant/routine
# split looks realistic, and it can inject anomalies on demand.
#
# USAGE:
#   python simulate_pico.py                      # steady readings to MQTT
#   python simulate_pico.py --interval 0.2       # fast, for load testing
#   python simulate_pico.py --anomaly-every 20   # inject a spike periodically
#   python simulate_pico.py --dry-run            # print instead of publishing
# =============================================================================

import argparse
import json
import math
import random
import time

# Topics + contract must match the real device path.
TOPIC_EVENTS = "edgesentry/events"
TOPIC_READINGS = "edgesentry/readings"

# Edge pre-filter thresholds -- mirror the firmware so behaviour matches.
TEMP_DELTA_C = 0.5
HUMIDITY_DELTA_PCT = 2.0
TEMP_RANGE = (-10.0, 50.0)
HUMIDITY_RANGE = (0.0, 100.0)

DEVICE_ID = "sim-0001"   # distinct id so simulated data is easy to filter out

# =============================================================================
# =============================================================================
# Fixes the saturation bug: anomalies now DECAY back toward a baseline instead
# of accumulating until they hit the clamps and stick there forever.
#
# Model: the sensor reads (baseline + offset), where
#   - baseline drifts slowly (sine + noise), like ambient room conditions
#   - offset is spiked by an anomaly, then decays exponentially back to zero,
#     the way real humidity falls after you stop breathing on the sensor
# =============================================================================

class Sensor:
    """Generates plausible temp/humidity: slow ambient drift plus decaying
    anomaly spikes. Mirrors the firmware's pre-filter so significant/routine
    tagging matches the real device."""

    # How fast an anomaly fades. 0.7 = each reading keeps 70% of the previous
    # offset, so a spike visibly decays over ~8-10 readings.
    DECAY = 0.7

    def __init__(self):
        # Ambient baseline -- typical indoor conditions.
        self.base_temp = 22.0
        self.base_humidity = 45.0
        # Transient offset from an injected anomaly (decays to zero).
        self.temp_offset = 0.0
        self.humidity_offset = 0.0
        self._t = 0.0
        self._last = {"temp": None, "humidity": None}

    def _drift(self):
        """Slow sinusoidal drift + small noise on the BASELINE only."""
        self._t += 1
        self.base_temp += 0.3 * math.sin(self._t / 20) + random.uniform(-0.1, 0.1)
        self.base_humidity += 0.5 * math.sin(self._t / 15) + random.uniform(-0.3, 0.3)
        # Keep the baseline in a realistic indoor band.
        self.base_temp = max(18.0, min(28.0, self.base_temp))
        self.base_humidity = max(30.0, min(60.0, self.base_humidity))

        # Anomaly offsets fade away -- this is what was missing before.
        self.temp_offset *= self.DECAY
        self.humidity_offset *= self.DECAY

    def inject_anomaly(self):
        """Simulate breathing on the sensor: a spike that will then decay."""
        self.humidity_offset += random.uniform(25, 40)
        self.temp_offset += random.uniform(3, 6)

    def _current(self):
        """Observed reading = baseline + transient offset, clamped to sensor range."""
        temp = max(-40.0, min(80.0, self.base_temp + self.temp_offset))
        humidity = max(0.0, min(99.9, self.base_humidity + self.humidity_offset))
        return round(temp, 2), round(humidity, 2)

    def is_significant(self, temp, humidity):
        """Same logic as firmware is_significant()."""
        if not (TEMP_RANGE[0] <= temp <= TEMP_RANGE[1]):
            return True, "temp_out_of_range"
        if not (HUMIDITY_RANGE[0] <= humidity <= HUMIDITY_RANGE[1]):
            return True, "humidity_out_of_range"
        if self._last["temp"] is None:
            return True, "first_reading"
        if abs(temp - self._last["temp"]) >= TEMP_DELTA_C:
            return True, "temp_delta"
        if abs(humidity - self._last["humidity"]) >= HUMIDITY_DELTA_PCT:
            return True, "humidity_delta"
        return False, "routine"

    def reading(self):
        """Produce one contract-shaped reading dict."""
        self._drift()
        temp, humidity = self._current()
        significant, reason = self.is_significant(temp, humidity)
        if significant:
            self._last["temp"] = temp
            self._last["humidity"] = humidity
        now = time.time()
        return {
            "device_id": DEVICE_ID,
            "ts": now,
            "temp_c": temp,
            "humidity_pct": humidity,
            "significant": significant,
            "reason": reason,
            "fw": "edgesentry-sim-1.0",
            "received_at": now,
        }

def parse_args():
    p = argparse.ArgumentParser(description="Simulate an EdgeSentry device")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--broker-port", type=int, default=1883)
    p.add_argument("--interval", type=float, default=5.0,
                   help="Seconds between readings (lower = faster/load test)")
    p.add_argument("--anomaly-every", type=int, default=0,
                   help="Inject an anomaly every N readings (0 = never)")
    p.add_argument("--count", type=int, default=0,
                   help="Stop after N readings (0 = run forever)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print readings instead of publishing to MQTT")
    return p.parse_args()


def main():
    args = parse_args()
    sensor = Sensor()

    client = None
    if not args.dry_run:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect(args.broker, args.broker_port, keepalive=60)
        client.loop_start()
        print(f"[sim] publishing to {args.broker}:{args.broker_port}")
    else:
        print("[sim] DRY RUN -- printing readings")

    n = 0
    try:
        while True:
            n += 1
            if args.anomaly_every and n % args.anomaly_every == 0:
                sensor.inject_anomaly()

            reading = sensor.reading()
            topic = TOPIC_EVENTS if reading["significant"] else TOPIC_READINGS

            if args.dry_run:
                print(f"[{topic}] {reading}")
            else:
                client.publish(topic, json.dumps(reading))
                print(f"[sim] {topic} temp={reading['temp_c']} "
                      f"hum={reading['humidity_pct']} sig={reading['significant']}")

            if args.count and n >= args.count:
                break
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[sim] stopping.")
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()