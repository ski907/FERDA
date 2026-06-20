import time
import json
import board
import analogio
import busio
import adafruit_vl53l0x

LOG_FILE = "/log_data.json"

def initialize_log_file():
    """Ensures the log file exists and is initialized as a JSON array."""
    try:
        # Try to open the file to check if it exists
        with open(LOG_FILE, "r") as f:
            pass
    except OSError:
        # If the file does not exist, create and initialize it
        with open(LOG_FILE, "w") as f:
            json.dump([], f)

def log_data(data):
    """Appends a data entry to the JSON log file."""
    with open(LOG_FILE, "r+") as f:
        # Load existing data
        log = json.load(f)
        
        # Add the new data entry
        log.append(data)
        
        # Write updated data back to the start of the file
        f.seek(0)
        json.dump(log, f)
        f.flush()  # Ensure data is written to the file

# Setup for I2C and rangefinder sensor
i2c = busio.I2C(board.SCL, board.SDA)
vl53 = adafruit_vl53l0x.VL53L0X(i2c)

# Define a constant for freeboard calculation (to be set during calibration later)
FREEBOARD_CONSTANT = 300  # Replace 300 with your calibration constant as needed

def measure_range():
    """Measures distance using the VL53L0X sensor."""
    return vl53.range  # Returns distance in millimeters

def get_battery_voltage():
    """Measures battery voltage."""
    # Setup the analog input pin connected to the battery monitor
    battery_pin = analogio.AnalogIn(board.VOLTAGE_MONITOR)  # Replace with your actual board pin
    measured_voltage = battery_pin.value * 3.3 / 65535  # Scale ADC reading to voltage
    measured_voltage *= 2  # Adjust for the voltage divider (if you’re using one)
    battery_pin.deinit()  # Deinitialize after reading to save power
    return round(measured_voltage, 2)  # Round to 2 decimal places for display

def collect_sensor_data():
    """Collects actual sensor data from the VL53L0X rangefinder and battery monitor."""
    
    # Measure range using the VL53L0X sensor
    range_val = measure_range()
    
    # Measure battery voltage
    battery_val = get_battery_voltage()
    
    # Calculate freeboard based on the constant and range measurement
    freeboard_val = FREEBOARD_CONSTANT - range_val  # Adjust as necessary for calibration
    
    # Create a data entry with a timestamp
    return {
        "timestamp": time.time(),
        "range": range_val,
        "battery": battery_val,
        "freeboard": freeboard_val
    }