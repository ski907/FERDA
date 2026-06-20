import wifi
import socketpool
import mdns
import time
import os
import logger  # Import the logger module

# Initialize the log file
logger.initialize_log_file()

class SimpleServer:
    def __init__(self):
        wifi.radio.start_ap(WIFI_SSID, password=WIFI_PASSWORD)
        self.mdns_server = mdns.Server(wifi.radio)
        self.mdns_server.hostname = "ferda"
        self.mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=HTTP_PORT)
        
        self.pool = socketpool.SocketPool(wifi.radio)
        self.server = self.pool.socket()
        self.server.bind(('0.0.0.0', HTTP_PORT))
        self.server.listen(1)
        
        # Set the server socket to non-blocking mode
        self.server.setblocking(False)
        
        self.last_log_time = time.monotonic()  # Start time for logging

    def send_response(self, conn, response):
        chunk_size = 512
        for i in range(0, len(response), chunk_size):
            conn.send(response[i:i + chunk_size])
            time.sleep(0.05)  # Small delay between chunks to manage ESP32 limitations

    def handle_request(self, conn, request_str):
        if "GET /monitor.js" in request_str:
            # Serve the JavaScript file from the filesystem
            try:
                with open("monitor.js", "r") as f:
                    js_content = f.read()
                js_response = f"HTTP/1.1 200 OK\r\nContent-Type: application/javascript\r\nContent-Length: {len(js_content)}\r\n\r\n{js_content}".encode()
                self.send_response(conn, js_response)
            except OSError:
                # If the file is not found or can't be read
                error_response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nFile not found".encode()
                self.send_response(conn, error_response)
        
        elif "GET /log_data.json" in request_str:
            # Serve the JSON file with logged data
            try:
                with open("log_data.json", "r") as f:
                    json_content = f.read()
                json_response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(json_content)}\r\n\r\n{json_content}".encode()
                self.send_response(conn, json_response)
            except OSError:
                error_response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nFile not found".encode()
                self.send_response(conn, error_response)

        else:
            # Serve the HTML content
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>FERDA Monitor</title>
                <style>
                    body { font-family: Arial; background: #f0f0f0; margin: 0; }
                    .container { margin: 10px; padding: 10px; background: white; border-radius: 5px; }
                    .value-box { display: flex; gap: 15px; margin-bottom: 20px; }
                    .value-box div { font-size: 18px; }
                    canvas { width: 100%; height: 200px; background: #fff; margin-bottom: 10px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>FERDA Monitor</h1>

                    <!-- Current value displays -->
                    <div class="value-box">
                        <div><strong>Range:</strong> <span id="currentRange">-- mm</span></div>
                        <div><strong>Battery:</strong> <span id="currentBattery">-- V</span></div>
                        <div><strong>Freeboard:</strong> <span id="currentFreeboard">-- mm</span></div>
                    </div>

                    <!-- Plot canvases -->
                    <canvas id="rangeChart"></canvas>
                    <canvas id="batteryChart"></canvas>
                    <canvas id="freeboardChart"></canvas>
                </div>

                <!-- Link external JavaScript file -->
                <script src="monitor.js"></script>
            </body>
            </html>
            """
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(html_content)}\r\n\r\n{html_content}".encode()
            self.send_response(conn, response)

    def log_periodically(self):
        # Log data every 5 seconds
        current_time = time.monotonic()
        if current_time - self.last_log_time >= 5:
            data = logger.collect_sensor_data()
            print(data)  # Print the collected data for debugging
            logger.log_data(data)
            print(f"Data logged at {current_time:.2f} seconds since start")  # Print the time since start
            self.last_log_time = current_time  # Reset the timer

    def run(self):
        print("Server is running!")
        print(f"Connect to WiFi: {WIFI_SSID}")
        print(f"Then visit: http://ferda.local or http://{wifi.radio.ipv4_address_ap}")
        
        while True:
            # Perform logging regardless of network state
            self.log_periodically()  # Check if it's time to log

            # Handle network requests (non-blocking)
            try:
                conn, addr = self.server.accept()
                try:
                    request = bytearray(1024)
                    bytes_received = conn.recv_into(request)
                    if bytes_received > 0:
                        request_str = request[:bytes_received].decode("utf-8")
                        self.handle_request(conn, request_str)
                finally:
                    conn.close()
            except OSError as e:
                # Handle non-blocking accept exception
                pass  # No connection is pending, move on
            # Short sleep to yield control and prevent CPU hogging
            time.sleep(0.01)

# Configuration
WIFI_SSID = "FERDA_AP"
WIFI_PASSWORD = "strong_password"
HTTP_PORT = 80

# Start the server
server = SimpleServer()
server.run()
