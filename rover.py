import serial
import time
import json

# Load config
with open("config.json", "r") as f:
    config = json.load(f)

port = config["port_rover"]
baud = config["baudrate"]

ser = serial.Serial(port, baud, timeout=1)
print("[Rover] Listening for messages...")

while True:
    data = ser.readline().decode("utf-8").strip()
    if data:
        try:
            parts = data.split("$")
            msg_id = int(parts[0])
            send_time = float(parts[1])
            payload = parts[2]

            recv_time = time.time()
            # Rover responds with same msg_id + timestamps
            response = f"{msg_id}${send_time}${recv_time}"
            ser.write(response.encode("utf-8"))
            print(f"[Rover] Received {msg_id}, responded back")
        except Exception as e:
            print(f"[Rover] Error parsing data: {data} ({e})")
