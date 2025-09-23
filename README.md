# RF Latency Testing Script

## Setup Instructions

1. **Install Python Dependencies**
   ```bash
   pip install pyserial
   ```

2. **Identify COM Ports**
   - Windows: Check Device Manager for COM ports (e.g., COM3, COM4)
   - Linux: Check `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.

## Usage

### On Base Laptop (Transmitter):
```bash
python rf_latency_test.py --mode base --port COM3
```

### On Rover Laptop (Receiver):
```bash
python rf_latency_test.py --mode rover --port COM4
```

### Optional Parameters:
```bash
python rf_latency_test.py --mode base --port COM3 --baudrate 921600 --debug
```

## Running the Test

1. **Start the rover first**:
   ```bash
   python rf_latency_test.py --mode rover --port COM4
   ```

2. **Then start the base** (within a few seconds):
   ```bash
   python rf_latency_test.py --mode base --port COM3 --baudrate 921600
   ```

3. **Wait for synchronization**: The scripts will sync with each other automatically.

4. **Test execution**: The base will send test data in multiple sizes (64, 128, 256, 512, 1024 bytes), each size tested 10 times for accuracy.

## Output

Results are saved to `output.json` in this format:

```json
{
  "data": [
    {
      "timestamp": "2025-09-24T10:30:00.123456",
      "timestamp_ns": 1727168200123456789,
      "location": {
        "base_coordinate": "0.000000,0.000000",
        "rover_coordinate": "0.000000,0.000000"
      },
      "64": {
        "latency": "1.25ms"
      },
      "128": {
        "latency": "2.30ms"
      },
      "256": {
        "latency": "4.20ms"
      },
      "512": {
        "latency": "8.80ms"
      },
      "1024": {
        "latency": "15.40ms"
      }
    }
  ]
}
```

## Key Features

- **Half-duplex communication**: Properly handles timing for half-duplex RF modules
- **Accurate timing**: Uses nanosecond timestamps for precise latency measurements
- **Multiple test sizes**: Tests 64, 128, 256, 512, and 1024 byte packets
- **Statistical averaging**: Each packet size is tested 10 times for accuracy
- **GPS placeholder**: `get_gps()` function ready for GPS integration
- **JSON logging**: Results append to `output.json` for historical tracking
- **Synchronization**: Automatic sync between base and rover before testing

## Troubleshooting

- **Connection issues**: Check COM port names and ensure RF modules are properly connected
- **Sync failures**: Make sure both scripts start within a few seconds of each other
- **Timeout errors**: Increase the timeout value in the script if your RF link is slow
- **Permission errors**: On Linux, you may need `sudo` or add user to `dialout` group

## GPS Integration

To implement GPS functionality, modify the `get_gps()` function to interface with your GPS module/service and return actual coordinates in the format:

```python
{
    "latitude": "40.123456",
    "longitude": "-74.123456", 
    "altitude": "100.5"
}
```