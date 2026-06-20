import time
import board
import neopixel
import wifi
import socketpool
import busio
import adafruit_vl53l0x
import mdns

from analogio import AnalogIn


# Setup Wi-Fi as an access point
wifi.radio.start_ap("FERDA_AP", password="strong_password")

# Initialize mDNS with a custom hostname
mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = "ferda"  # Access at ferda.local
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)

# Initialize NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1)

# Initialize I2C bus for rangefinder
i2c = busio.I2C(board.SCL, board.SDA)
vl53 = adafruit_vl53l0x.VL53L0X(i2c)

# Load the HTML from the file
with open("/index.html", "r") as f:
    html = f.read()

# Set default measurement frequency
measurement_interval = 10  # Default to 10 seconds

def update_neopixel_color(r, g, b):
    pixel.fill((r, g, b))
    
def measure_range():
    return vl53.range

def get_battery_voltage():
    # Set up the analog pin connected to the battery (use the correct pin for your board)
    battery_pin = AnalogIn(board.VOLTAGE_MONITOR)  # Replace with your actual battery input pin
    measured_voltage = battery_pin.value * 3.3 / 65535  # Scale ADC reading to voltage
    measured_voltage *= 2  # Adjust for the voltage divider (if you’re using one)
    battery_pin.deinit()  # Deinitialize to save power
    return round(measured_voltage, 2)  # Round to 2 decimal places for display

# Create the socket pool and server socket outside the main loop
pool = socketpool.SocketPool(wifi.radio)
server = None

# Track the last measurement time
last_measurement_time = time.monotonic()

while True:
    current_time = time.monotonic()
    
    # Only perform a measurement if the interval has passed
    if current_time - last_measurement_time >= measurement_interval:
        range_value = measure_range()
        last_measurement_time = current_time
        print("Measured Range:", range_value)

    try:
        # Initialize and bind the server if it hasn't been done already
        if server is None:
            server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            server.bind(("0.0.0.0", 80))  # Use port 80
            server.listen(1)

        conn, addr = server.accept()
        
        # Use `recv_into` with a bytearray buffer
        request = bytearray(1024)
        conn.recv_into(request)
        request_str = request.decode("utf-8")
        
        # Process the HTTP request
        print("Request received:", request_str)

        # Serve HTML page
        if "GET / " in request_str:
            conn.send("HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close\n\n")
            conn.send(html)

        # Serve range data as JSON
        elif "GET /range" in request_str:
            print("Serving range data")  # Debug print to confirm endpoint reached
            json_response = f'{{"range": {range_value}}}'
            conn.send("HTTP/1.1 200 OK\nContent-Type: application/json\nContent-Length: " + str(len(json_response)) + "\nConnection: close\n\n")
            conn.send(json_response)
            print(f"Sent range: {range_value}")  # Debug print to verify data sent
            
        # Serve battery voltage as JSON
        elif "GET /battery" in request_str:
            voltage = get_battery_voltage()
            json_response = f'{{"voltage": {voltage}}}'
            conn.send("HTTP/1.1 200 OK\nContent-Type: application/json\nConnection: close\n\n")
            conn.send(json_response)
            print(f"Sent battery voltage: {voltage}")

        # Update measurement frequency
        elif "GET /set_interval?" in request_str:
            parts = request_str.split(" ")
            path = parts[1].split("?")[1]
            params = dict(param.split("=") for param in path.split("&"))
            measurement_interval = int(params.get("interval", measurement_interval))
            print(f"Updated measurement interval to {measurement_interval} seconds")
            json_response = f'{{"interval": {measurement_interval}}}'
            conn.send("HTTP/1.1 200 OK\nContent-Type: application/json\nContent-Length: " + str(len(json_response)) + "\nConnection: close\n\n")
            conn.send(json_response)

        # Fallback response for unexpected requests
        else:
            print("Unhandled request")
            conn.send("HTTP/1.1 404 Not Found\nContent-Type: text/plain\nConnection: close\n\n")
            conn.send("404 Not Found")

        conn.close()

    except OSError as e:
        print("Error:", e)
        time.sleep(1)
    
    finally:
        # Only close the connection, not the server, to keep it bound
        if conn:
            conn.close()  

