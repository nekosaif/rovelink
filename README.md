# XBee Network Benchmark Tool

A comprehensive Python tool for benchmarking XBee module performance, including latency and bandwidth tests with bidirectional communication support.

---

## Features

* **Automatic Bandwidth Measurement**
* **Latency Testing** with configurable data sizes and intervals
* **Bidirectional Communication** support (Master/Slave)
* **Real-time Statistics**
* **Result Reporting** between nodes

---

## Requirements

* Python 3.x
* `pyserial` module

  ```bash
  pip install pyserial
  ```
* XBee modules connected to your system via serial (COM) ports

---

## Installation

1. Clone or download this repository.
2. Ensure Python 3 and `pyserial` are installed.
3. Connect XBee modules to available COM ports.

---

## Usage

```bash
python xbee_benchmark.py --port COM3 --mode master
python xbee_benchmark.py --port COM4 --mode slave
```

### Command-line Options

| Option              | Description                                     | Default  |
| ------------------- | ----------------------------------------------- | -------- |
| `--port` / `-p`     | Serial port for XBee (e.g., COM3, /dev/ttyUSB0) | Required |
| `--baudrate` / `-b` | Baud rate for serial communication              | 9600     |
| `--mode` / `-m`     | Operation mode (`master` or `slave`)            | master   |
| `--node-id` / `-n`  | Node identifier (single character)              | A        |

---

## Node Modes

### Master Node

* Initiates tests and sends `PING` messages for latency measurement.
* Sends continuous data for bandwidth measurement.
* Collects and displays results from Slave node.
* Example:

  ```bash
  python xbee_benchmark.py --port COM3 --mode master
  ```

### Slave Node

* Responds to Master requests:

  * Replies with `PONG` to `PING`
  * Receives data for bandwidth calculation
* Example:

  ```bash
  python xbee_benchmark.py --port COM4 --mode slave
  ```

---

## Message Format

All messages use the following standardized format:

```
$$[MSG_TYPE][NODE_ID][TIMESTAMP][DATA_SIZE][PAYLOAD]##
```

* `MSG_TYPE`: 4-byte identifier (`PING`, `PONG`, `DATA`, `SYNC`, `RSLT`)
* `NODE_ID`: Single character node identifier
* `TIMESTAMP`: 8-byte float representing Unix time
* `DATA_SIZE`: 2-byte unsigned short
* `PAYLOAD`: Optional message payload
* Markers `$$` and `##` denote message start and end

---

## Tests

### Latency Test

* Sends `PING` messages and calculates round-trip time from `PONG`.
* Configurable:

  * `data_size` (bytes)
  * `interval` (seconds)
  * Duration (default 10–15s per test)
* Example output:

  ```
  Avg Latency: 12.34 ms
  Min Latency: 10.12 ms
  Max Latency: 15.67 ms
  ```

### Bandwidth Test

* Continuously sends `DATA` messages to measure throughput.
* Reports:

  * Bytes sent
  * Time elapsed
  * Bandwidth (bytes/sec and KB/s)
* Example output:

  ```
  Bytes sent: 10240
  Bandwidth: 512.00 KB/s
  ```

---

## Real-time Statistics

* Updates every 5 seconds
* Displays:

  * TX/RX bytes
  * Receive bandwidth
  * Recent average latency (last 10 measurements)

---

## Comprehensive Benchmark

* Master node runs multiple latency tests and a bandwidth test.
* Slave node continuously responds.
* Master node collects results and sends them to Slave.
* Results include:

  * Node ID and mode
  * Latency test details
  * Bandwidth measurements
  * Timestamp

---

## Example Results

```
=== Results from Node B ===
Node ID: B
Mode: slave
Timestamp: 2025-09-18T15:00:00

--- Latency Test Results ---
Data Size: 8 bytes, Interval: 0.1s, Avg Latency: 12.34 ms
Data Size: 16 bytes, Interval: 0.1s, Avg Latency: 13.56 ms

--- Bandwidth Test Results ---
Duration: 20.00 seconds
Bytes Sent: 10240
Bandwidth: 512.00 KB/s
```

---

## Stopping the Tool

* Press `Ctrl+C` to stop either Master or Slave node.
* The tool will gracefully close serial connections.

---

## Notes

* Ensure COM ports are correctly identified before running.
* Slave node must be running before starting Master node for proper communication.
* Test parameters (data sizes, intervals, durations) can be adjusted in the script.
