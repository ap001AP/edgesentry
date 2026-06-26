#!/usr/bin/env python3
# =============================================================================
# EdgeSentry - Serial-to-MQTT Bridge (runs on the host)
# =============================================================================
# Reads newline-delimited JSON from the Pico over USB serial, enriches each
# reading with a host-side authoritative timestamp, and republishes it to MQTT.
#
# This is the "adapter" layer (ADR 0001): the Pico speaks serial, the cloud
# speaks MQTT, and this bridge translates between them.
#
# Routing mirrors the firmware's edge pre-filter:
#   significant == true  -> TOPIC_EVENTS   (priority; the LLM watches these)
#   significant == false -> TOPIC_READINGS (bulk; stored + drift-sampled)
#   error present        -> TOPIC_HEALTH   (faults/telemetry)
#
# USAGE:
#   python serial_to_mqtt.py --port /dev/tty.usbmodem1101 --dry-run
#   python serial_to_mqtt.py --port /dev/tty.usbmodem1101 --broker localhost
# =============================================================================
 
import argparse
import json
import sys
import time 
import serial

TOPIC_EVENTS = "edgesentry/events"
TOPIC_READINGS = "edgesentry/readings"
TOPIC_HEALTH = "edgesentry/health"

def parse_args():
    p = argparse.ArgumentParser(description="Bridge Pico serial output to MQTT")
    p.add_argument("--port", required=True, help="Serial port (e.g. /dev/tty.usbmodem14201")
    p.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    p.add_argument("--broker", default="localhost", help="MQTT broker host (ignore in --dry-run)")
    p.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port")
    p.add_argument("--dry-run", action="store_true", help="Parse + print readings without connecting to MQTT")
    return p.parse_args()

def classify_topic(reading):
    """Decide which MQTT topic a reading belongs on, based on its content."""
    if "error" in reading:
        return TOPIC_HEALTH
    elif reading.get("significant"):
        return TOPIC_EVENTS
    else:
        return TOPIC_READINGS

def enrich(reading):
    """Add host-side context the constrained device can't provide reliably.
 
    The Pico has no real-time clock, so its `ts` is device-relative, not true
    wall-clock time. The host DOES know the real time, so we add an
    authoritative `received_at`. (Pushing a responsibility to the layer that's
    actually capable of it.)
    """
    reading["received_at"] = time.time()
    return reading

def make_mqtt_client(broker, broker_port):
    """Create + connect a paho-mqtt client. Imported lazily so --dry-run
    works even if paho isn't installed yet."""
    import paho.mqtt.client as mqtt
    client = mqtt.Client()
    client.connect(broker, broker_port, keepalive=60)
    client.loop_start()  # background thread handles network traffic 
    return client

def run():
    args = parse_args()

    # Open the serial port
    # We can test against real hardware without any broker present
    try:
        ser = serial.Serial(args.port, args.baud, timeout=2)
    except serial.SerialException as e:
        print(f"[bridge] could not open serial port {args.port}: {e}", file=sys.stderr)
        sys.exit(1)

    client = None
    if not args.dry_run:
        client = make_mqtt_client(args.broker, args.broker_port)
        print(f"[bridge] connected to MQTT broker {args.broker}:{args.broker_port}")
    else:
        print("[bridge] running in dry-run mode; no MQTT connection will be made")
    
    print(f"[bridge] reading from {args.port} at {args.baud} baud. Press Ctrl-C to exit.")

    try:
        while True:
            raw = ser.readline()  # reads up to a newline (NDJSON)
            if not raw:
                continue          # timeout with no data; loo again

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Each line should be one JSON object. Bad lines (electrical noise, partial reads on startup)
            # are logged and skipped 
            try:
                reading = json.loads(line)
            except json.JSONDecodeError:
                print(f"[bridge] skipping non-JSON line: {line!r}", file=sys.stderr)
                continue

            reading = enrich(reading)
            topic = classify_topic(reading)

            if args.dry_run:
                print(f"[{topic}] {reading}")
            else:
                client.publish(topic, json.dumps(reading))
    
    except KeyboardInterrupt:
        print("\n[bridge] exiting on user request")
    finally:
        ser.close()
        if client is not None:
            client.loop_stop()
            client.disconnect()

if __name__ == "__main__":
    run()