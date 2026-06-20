import time
import json
import os
import board
import analogio
import busio
import adafruit_vl53l0x

LOG_FILE = "/log_data.jsonl"
OLD_LOG_FILE = "/log_data.json"
LOG_SIZE_LIMIT = 50000  # bytes; ~500 entries at ~100 bytes each (~41 hrs at 5 s)

i2c = busio.I2C(board.SCL, board.SDA)
vl53 = adafruit_vl53l0x.VL53L0X(i2c)


def initialize_log_file():
    _migrate_old_log()
    try:
        os.stat(LOG_FILE)
    except OSError:
        with open(LOG_FILE, "w") as f:
            pass


def _migrate_old_log():
    try:
        os.stat(OLD_LOG_FILE)
    except OSError:
        return
    try:
        with open(OLD_LOG_FILE, "r") as f:
            old_data = json.load(f)
        with open(LOG_FILE, "w") as f:
            for entry in old_data:
                f.write(json.dumps(entry) + "\n")
        os.remove(OLD_LOG_FILE)
        print("Migrated log_data.json -> log_data.jsonl")
    except Exception as e:
        print("Migration error:", e)


def _rotate_log():
    """Stream through the log, discard the oldest half, write remainder to a temp file."""
    tmp = LOG_FILE + ".tmp"
    count = 0
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                if line.strip():
                    count += 1
    except OSError:
        return

    skip = count // 2
    seen = 0
    try:
        with open(tmp, "w") as out:
            with open(LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        if seen >= skip:
                            out.write(line)
                        seen += 1
        os.remove(LOG_FILE)
        os.rename(tmp, LOG_FILE)
        print(f"Log rotated: kept {count - skip} entries")
    except Exception as e:
        print("Rotation error:", e)
        try:
            os.remove(tmp)
        except OSError:
            pass


def log_data(entry):
    try:
        if os.stat(LOG_FILE)[6] > LOG_SIZE_LIMIT:
            _rotate_log()
    except OSError:
        pass
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_last_entries(n=60):
    """Read last N entries without loading the whole file into memory at once."""
    window = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    if len(window) >= n:
                        window.pop(0)
                    window.append(line)
    except OSError:
        return []
    result = []
    for line in window:
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return result


def measure_range():
    return vl53.range


def get_battery_voltage():
    pin = analogio.AnalogIn(board.VOLTAGE_MONITOR)
    v = pin.value * 3.3 / 65535 * 2
    pin.deinit()
    return round(v, 2)


def collect_sensor_data(settings):
    raw = measure_range()
    battery = get_battery_voltage()
    freeboard = raw - settings.get("range_offset_mm", 0) - settings.get("sensor_to_flange_mm", 0)
    return {
        "timestamp": time.time(),
        "range": raw,
        "battery": battery,
        "freeboard": round(freeboard, 1)
    }
