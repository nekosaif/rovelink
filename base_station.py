import serial
import time
import json
import random
import string

# Load config
with open("config.json", "r") as f:
    config = json.load(f)

interval = config["transmission_interval"]
data_size = config["data_size"]
port = config["port_base"]
baud = config["baudrate"]

ser = serial.Serial(port, baud, timeout=1)
message_counter = 0

def random_ascii(size):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(size))

print("[Base Station] Started communication...")

while True:
    # Prepare message
    message_counter += 1
    payload = random_ascii(data_size)
    send_time = time.time()
    msg = f"{message_counter}${send_time}${payload}"
    ser.write(msg.encode("utf-8"))
    print(f"[Base Station] Sent {message_counter}")

    # Wait for rover response
    response = ser.readline().decode("utf-8").strip()
    if response:
        try:
            parts = response.split("$")
            recv_id = int(parts[0])
            sent_time = float(parts[1])
            recv_time = float(parts[2])  # Rover appended its receive timestamp
            delay = recv_time - sent_time
            print(f"[Base Station] Message {recv_id} Delay {delay:.6f} seconds")
        except Exception as e:
            print(f"[Base Station] Error parsing response: {response} ({e})")

    time.sleep(interval)
