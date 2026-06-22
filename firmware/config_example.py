# =============================================================================
# EdgeSentry - Pico Firmware Config 
# =============================================================================
# Copy this file to `config.py` on the Pico to override the firmware defaults.
# This serial version has NO secrets (no wifi/broker creds), just settings for the edge pre-filter.
#
# If config.py is absent, firmware/main.py falls back to these same defaults.
# =============================================================================

# --- Pin wiring --------------------------------------------------------------
# GPIO number the DHT22 DATA line is connected to.
# GP15 == physical pin 20. 
DATA_PIN = 15

# --- Sampling cadence --------------------------------------------------------
# Seconds between sensor reads. The DHT22 requires at least ~2s between reads.
READ_INTERVAL_S = 5

# --- Edge pre-filter settings ------------------------------------------------
# A reading is flagged "significant" if it moved by at least these amounts
# since the last flagged reading. Lower = more sensitive = more events sent.
TEMP_DELTA_C = 0.5           # degrees Celsius
HUMIDITY_DELTA_PCT = 2.0     # percent relative humidity

# Hard out-of-band limits. Any reading outside these is always flagged, regardless of delta.
# It may be a real anomaly or a sensor fault.
TEMP_RANGE = (-10, 50)       # (min_c, max_c)
HUMIDITY_RANGE = (0, 100)    # (min_pct, max_pct)