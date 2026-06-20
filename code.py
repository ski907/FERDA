import wifi
import socketpool
import mdns
import time
import os
import json
import errno
import logger

SETTINGS_FILE = "/settings.json"

DEFAULT_SETTINGS = {
    "wifi_ssid": "FERDA_AP",
    "wifi_password": "strong_password",
    "sensor_to_flange_mm": 100,
    "cap_distance_mm": 30,
    "range_offset_mm": 0,
    "ice_thickness_cm": 0,
    "expected_freeboard_mm": 0,
    "alarm_threshold_mm": 20,
    "log_interval_sec": 5,
}


def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            s = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            if k not in s:
                s[k] = v
        return s
    except OSError:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


def url_decode(s):
    result = []
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                result.append(chr(int(s[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        if s[i] == "+":
            result.append(" ")
        else:
            result.append(s[i])
        i += 1
    return "".join(result)


def parse_request(request_str):
    """Return (method, path, params_dict) from a raw HTTP request string."""
    try:
        first_line = request_str.split("\r\n")[0]
        parts = first_line.split(" ")
        method = parts[0]
        path_qs = parts[1] if len(parts) > 1 else "/"
    except Exception:
        return "GET", "/", {}

    if "?" in path_qs:
        path, qs = path_qs.split("?", 1)
    else:
        path, qs = path_qs, ""

    params = {}
    for pair in qs.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[url_decode(k)] = url_decode(v)

    return method, path, params


class SimpleServer:
    def __init__(self, settings):
        self.settings = settings
        wifi.radio.start_ap(settings["wifi_ssid"], password=settings["wifi_password"])
        self.mdns_server = mdns.Server(wifi.radio)
        self.mdns_server.hostname = "ferda"
        self.mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)

        self.pool = socketpool.SocketPool(wifi.radio)
        self.server = self.pool.socket()
        self.server.bind(("0.0.0.0", 80))
        self.server.listen(1)
        self.server.setblocking(False)
        self.last_log_time = time.monotonic()

    def _send(self, conn, data):
        chunk_size = 512
        for i in range(0, len(data), chunk_size):
            conn.send(data[i:i + chunk_size])
            time.sleep(0.05)

    def _respond(self, conn, body, content_type="application/json"):
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        header = ("HTTP/1.1 200 OK\r\nContent-Type: " + content_type +
                  "\r\nContent-Length: " + str(len(body_bytes)) + "\r\n\r\n").encode()
        self._send(conn, header + body_bytes)

    def _serve_file(self, conn, filename, content_type):
        try:
            with open(filename, "r") as f:
                content = f.read()
            self._respond(conn, content, content_type)
        except OSError:
            self._send(conn, b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\n\r\nNot found")

    # --- Request handlers ---

    def _handle_log_json(self, conn):
        entries = logger.read_last_entries(60)
        self._respond(conn, json.dumps(entries))

    def _handle_latest(self, conn):
        entries = logger.read_last_entries(1)
        body = json.dumps(entries[0]) if entries else "{}"
        self._respond(conn, body)

    def _handle_config_get(self, conn):
        self._respond(conn, json.dumps(self.settings))

    def _handle_save_config(self, conn, params):
        numeric_keys = ("sensor_to_flange_mm", "alarm_threshold_mm", "log_interval_sec", "cap_distance_mm")
        for key in numeric_keys:
            if key in params:
                try:
                    val = params[key]
                    self.settings[key] = float(val) if "." in val else int(val)
                except ValueError:
                    pass

        wifi_changed = False
        for key in ("wifi_ssid", "wifi_password"):
            if key in params and params[key] != self.settings.get(key):
                self.settings[key] = params[key]
                wifi_changed = True

        save_settings(self.settings)
        msg = "saved -- power cycle to apply WiFi changes" if wifi_changed else "saved"
        self._respond(conn, json.dumps({"status": msg}))

    def _handle_calibrate(self, conn, params):
        cap_mm = float(params.get("cap_mm", self.settings.get("cap_distance_mm", 30)))
        raw = logger.measure_range()
        offset = round(raw - cap_mm, 1)
        self.settings["range_offset_mm"] = offset
        self.settings["cap_distance_mm"] = cap_mm
        save_settings(self.settings)
        self._respond(conn, json.dumps({
            "raw_range_mm": raw,
            "cap_distance_mm": cap_mm,
            "range_offset_mm": offset,
            "status": "ok",
        }))

    def _handle_set_ice(self, conn, params):
        if "ice_cm" not in params:
            self._respond(conn, json.dumps({"error": "ice_cm required"}))
            return
        ice_cm = float(params["ice_cm"])
        expected_mm = round(ice_cm * 10 * 0.083, 1)
        self.settings["ice_thickness_cm"] = ice_cm
        self.settings["expected_freeboard_mm"] = expected_mm
        save_settings(self.settings)
        self._respond(conn, json.dumps({
            "ice_thickness_cm": ice_cm,
            "expected_freeboard_mm": expected_mm,
            "status": "ok",
        }))

    def _handle_verify(self, conn, params):
        expected_mm = self.settings.get("expected_freeboard_mm", 0)
        raw = logger.measure_range()
        measured_mm = round(
            raw - self.settings.get("range_offset_mm", 0) - self.settings.get("sensor_to_flange_mm", 0),
            1
        )
        diff = round(measured_mm - expected_mm, 1)
        pct = round(abs(diff) / expected_mm * 100, 1) if expected_mm > 0 else 0
        self._respond(conn, json.dumps({
            "expected_freeboard_mm": expected_mm,
            "measured_freeboard_mm": measured_mm,
            "difference_mm": diff,
            "difference_pct": pct,
            "status": "ok" if pct < 25 else "check_sensor",
        }))

    # --- Main loop ---

    def handle_request(self, conn, request_str):
        _, path, params = parse_request(request_str)

        if path == "/monitor.js":
            self._serve_file(conn, "monitor.js", "application/javascript")
        elif path == "/log_data.json":
            self._handle_log_json(conn)
        elif path == "/latest.json":
            self._handle_latest(conn)
        elif path == "/config":
            self._handle_config_get(conn)
        elif path == "/save_config":
            self._handle_save_config(conn, params)
        elif path == "/calibrate":
            self._handle_calibrate(conn, params)
        elif path == "/set_ice":
            self._handle_set_ice(conn, params)
        elif path == "/verify":
            self._handle_verify(conn, params)
        else:
            self._serve_file(conn, "index.html", "text/html; charset=utf-8")

    def log_periodically(self):
        current_time = time.monotonic()
        interval = self.settings.get("log_interval_sec", 5)
        if current_time - self.last_log_time >= interval:
            data = logger.collect_sensor_data(self.settings)
            print(data)
            logger.log_data(data)
            self.last_log_time = current_time

    def run(self):
        print("Server running!")
        print("WiFi: " + self.settings["wifi_ssid"])
        print("URL: http://ferda.local or http://" + str(wifi.radio.ipv4_address_ap))

        while True:
            self.log_periodically()
            try:
                conn, addr = self.server.accept()
                try:
                    request = bytearray(1024)
                    n = conn.recv_into(request)
                    if n > 0:
                        self.handle_request(conn, request[:n].decode("utf-8"))
                finally:
                    conn.close()
            except OSError as e:
                if e.args[0] not in (errno.EAGAIN, errno.ECONNRESET):
                    print("Socket error:", e)
            time.sleep(0.01)


logger.initialize_log_file()
settings = load_settings()
server = SimpleServer(settings)
server.run()
