#!/usr/bin/env python3
"""
XBee Network Benchmark Tool (fixed)
Run one instance as master and the other as slave:
  Terminal 1: python xbee_benchmark.py --port COM3 --mode master --node-id A
  Terminal 2: python xbee_benchmark.py --port COM4 --mode slave  --node-id B
"""

import serial
import time
import threading
import argparse
import json
import statistics
import struct
from datetime import datetime
from collections import deque
import sys

class XBeeBenchmark:
    def __init__(self, port, baudrate=9600, mode='master', node_id='A'):
        self.port = port
        self.baudrate = baudrate
        self.mode = mode
        # node_id must be a single ascii character
        self.node_id = (node_id[:1]).encode('ascii', errors='ignore') or b'A'
        self.serial_conn = None
        self.running = False

        # Stats
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.start_time = time.time()
        self.latency_measurements = deque(maxlen=5000)
        self.bandwidth_measurements = deque(maxlen=100)

        # Test configuration (tweak as needed)
        self.test_data_sizes = [8, 32, 128, 512]  # bytes
        self.test_intervals = [0.1, 0.5, 1.0]  # seconds

        # Threads
        self.rx_thread = None
        self.stats_thread = None

        # Message types (4 bytes each)
        self.MSG_PING = b'PING'
        self.MSG_PONG = b'PONG'
        self.MSG_DATA = b'DATA'
        self.MSG_SYNC = b'SYNC'
        self.MSG_RESULT = b'RSLT'

    def connect(self):
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.5,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"[+] Connected to {self.port} @ {self.baudrate}")
            return True
        except Exception as e:
            print(f"[-] Failed to open {self.port}: {e}")
            return False

    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except:
                pass
            print("[+] Disconnected")

    def create_message(self, msg_type, payload: bytes = b'', timestamp: float = None):
        """
        Message layout:
        b'$$' (2)
        msg_type (4)
        node_id (1)
        timestamp (8) - little-endian double
        data_size (2) - unsigned short little-endian
        payload (data_size)
        b'##' (2)
        """
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")

        data_size = len(payload)
        timestamp_val = time.time() if timestamp is None else float(timestamp)
        timestamp_bytes = struct.pack('<d', timestamp_val)
        data_size_bytes = struct.pack('<H', data_size)

        message = b'$$' + msg_type + self.node_id[:1] + timestamp_bytes + data_size_bytes + payload + b'##'
        return message

    def parse_message(self, data: bytes):
        """Return dict or None if invalid"""
        try:
            if not data.startswith(b'$$') or not data.endswith(b'##'):
                return None
            content = data[2:-2]
            if len(content) < (4 + 1 + 8 + 2):
                return None
            msg_type = content[0:4]
            node_id = chr(content[4])
            timestamp = struct.unpack('<d', content[5:13])[0]
            data_size = struct.unpack('<H', content[13:15])[0]
            payload = content[15:15+data_size] if data_size > 0 else b''
            return {
                'type': msg_type,
                'node_id': node_id,
                'timestamp': timestamp,
                'data_size': data_size,
                'payload': payload,
                'rx_time': time.time()
            }
        except Exception as e:
            # don't crash on malformed packets
            print(f"[!] parse_message error: {e}")
            return None

    def send_message(self, msg_type, payload: bytes = b'', timestamp: float = None):
        """Build and write message; returns number of bytes written or -1"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return -1
        message = self.create_message(msg_type, payload, timestamp)
        try:
            written = self.serial_conn.write(message)
            self.tx_bytes += written
            return written
        except Exception as e:
            print(f"[!] send_message error: {e}")
            return -1

    def receive_loop(self):
        buf = b''
        while self.running:
            try:
                if self.serial_conn.in_waiting:
                    chunk = self.serial_conn.read(self.serial_conn.in_waiting)
                    if chunk:
                        buf += chunk
                        self.rx_bytes += len(chunk)
                        # extract full messages
                        while True:
                            start = buf.find(b'$$')
                            end = buf.find(b'##', start+2)
                            if start == -1 or end == -1:
                                break
                            msg = buf[start:end+2]
                            buf = buf[end+2:]
                            parsed = self.parse_message(msg)
                            if parsed:
                                self.handle_received_message(parsed)
                else:
                    time.sleep(0.005)
            except Exception as e:
                print(f"[!] receive_loop error: {e}")
                time.sleep(0.1)

    def handle_received_message(self, message):
        t = message['type']
        if t == self.MSG_PING:
            # Echo PONG but preserve the original PING timestamp to allow RTT measurement.
            # Use the original ping's timestamp in the PONG message header.
            payload = message['payload']
            original_ts = message['timestamp']
            self.send_message(self.MSG_PONG, payload=payload, timestamp=original_ts)

        elif t == self.MSG_PONG:
            # Calculate RTT: received_time - original_ping_timestamp
            rtt = (message['rx_time'] - message['timestamp']) * 1000.0  # ms
            self.latency_measurements.append(rtt)

        elif t == self.MSG_DATA:
            # Just receiving bulk data; rx_bytes is used to compute bandwidth
            pass

        elif t == self.MSG_SYNC:
            print(f"[i] SYNC from node {message['node_id']}")

        elif t == self.MSG_RESULT:
            try:
                results = json.loads(message['payload'].decode('utf-8'))
                print(f"\n=== Results from Node {message['node_id']} ===")
                self.print_results(results)
            except Exception as e:
                print(f"[!] Error parsing results payload: {e}")

    def run_latency_test(self, data_size, interval, duration=10):
        print(f"\n-- Latency test: size={data_size} bytes, interval={interval}s, dur={duration}s")
        self.latency_measurements.clear()
        payload = b'X' * data_size
        end_time = time.time() + duration
        sent = 0
        while time.time() < end_time and self.running:
            # Send a PING; create_message will stamp timestamp
            self.send_message(self.MSG_PING, payload=payload)
            sent += 1
            time.sleep(interval)
        # give some time for responses
        time.sleep(1.5)
        if self.latency_measurements:
            avg = statistics.mean(self.latency_measurements)
            mn = min(self.latency_measurements)
            mx = max(self.latency_measurements)
            print(f"Sent {sent} pings, Received {len(self.latency_measurements)} pongs")
            print(f"Latency ms - avg: {avg:.2f}, min: {mn:.2f}, max: {mx:.2f}")
            return {
                'data_size': data_size,
                'interval': interval,
                'avg_latency': avg,
                'min_latency': mn,
                'max_latency': mx,
                'packets': len(self.latency_measurements)
            }
        else:
            print("[!] No latency samples collected")
            return None

    def run_bandwidth_test(self, duration=15, data_size=512, send_interval=0.01):
        print(f"\n-- Bandwidth test: duration={duration}s, data_size={data_size} bytes")
        start_tx = self.tx_bytes
        t0 = time.time()
        payload = b'B' * data_size
        while time.time() - t0 < duration and self.running:
            self.send_message(self.MSG_DATA, payload=payload)
            # small pause to avoid flooding USB/serial buffers; tune as needed
            time.sleep(send_interval)
        elapsed = time.time() - t0
        bytes_sent = self.tx_bytes - start_tx
        bps = bytes_sent / elapsed if elapsed > 0 else 0
        kbps = bps / 1024.0
        print(f"[i] Sent {bytes_sent} bytes in {elapsed:.2f}s -> {bps:.2f} B/s ({kbps:.2f} KB/s)")
        return {'duration': elapsed, 'bytes_sent': bytes_sent, 'bandwidth_bps': bps, 'bandwidth_kbps': kbps}

    def print_statistics(self):
        while self.running:
            time.sleep(5)
            elapsed = time.time() - self.start_time
            rx_bps = self.rx_bytes / elapsed if elapsed > 0 else 0
            rx_kbps = rx_bps / 1024.0
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] stats: TX={self.tx_bytes} RX={self.rx_bytes} RX_bw={rx_kbps:.2f} KB/s")
            if self.latency_measurements:
                recent = list(self.latency_measurements)[-10:]
                print(f" recent latency avg (last {len(recent)}): {statistics.mean(recent):.2f} ms")

    def run_comprehensive_test(self):
        print(f"\n=== Starting XBee benchmark node {self.node_id.decode('ascii',errors='ignore')} ({self.mode}) ===")
        time.sleep(1.0)

        results = {'node_id': self.node_id.decode('ascii',errors='ignore'), 'mode': self.mode, 'timestamp': datetime.now().isoformat(), 'latency_tests': [], 'bandwidth_test': None}

        if self.mode == 'master':
            print("[i] Acting as MASTER - initiating tests")
            # send SYNC
            self.send_message(self.MSG_SYNC, payload=b'')
            time.sleep(0.5)

            for sz in self.test_data_sizes:
                for iv in self.test_intervals:
                    if not self.running:
                        break
                    res = self.run_latency_test(sz, iv, duration=8)
                    if res:
                        results['latency_tests'].append(res)
                    time.sleep(1.0)
                if not self.running:
                    break

            bw = self.run_bandwidth_test(duration=15, data_size=256, send_interval=0.005)
            results['bandwidth_test'] = bw

            # send results to other node
            json_bytes = json.dumps(results).encode('utf-8')
            self.send_message(self.MSG_RESULT, payload=json_bytes)
            print("[i] Master finished tests")

        else:
            print("[i] Acting as SLAVE - waiting and responding (automatic reply to PING enabled)")
            # Slave waits for master to finish and optionally runs its own bandwidth test
            # We'll wait some time then run a small bandwidth test
            wait_for = 20
            print(f"[i] Slave waiting {wait_for}s for master to run tests")
            time.sleep(wait_for)
            if self.running:
                bw = self.run_bandwidth_test(duration=10, data_size=256, send_interval=0.01)
                results['bandwidth_test'] = bw
                # send results back
                jb = json.dumps(results).encode('utf-8')
                self.send_message(self.MSG_RESULT, payload=jb)

        return results

    def print_results(self, results):
        print("---- Test Results ----")
        print(f"Node: {results.get('node_id')} Mode: {results.get('mode')} Time: {results.get('timestamp')}")
        if results.get('latency_tests'):
            print("Latency Tests:")
            for t in results['latency_tests']:
                print(f" size={t['data_size']} interval={t['interval']} avg={t['avg_latency']:.2f}ms")
        if results.get('bandwidth_test'):
            bw = results['bandwidth_test']
            print(f"Bandwidth: {bw['bandwidth_kbps']:.2f} KB/s over {bw['duration']:.2f}s")

    def start(self):
        if not self.connect():
            return
        self.running = True
        self.start_time = time.time()

        self.rx_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.stats_thread = threading.Thread(target=self.print_statistics, daemon=True)
        self.rx_thread.start()
        self.stats_thread.start()

        try:
            results = self.run_comprehensive_test()
            print("\n=== Local final results ===")
            self.print_results(results)
            # allow a short window to receive peer results
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n[!] Interrupted by user")
        finally:
            self.running = False
            time.sleep(0.2)
            self.disconnect()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', '-p', required=True)
    p.add_argument('--baudrate', '-b', type=int, default=9600)
    p.add_argument('--mode', '-m', choices=['master', 'slave'], default='master')
    p.add_argument('--node-id', '-n', default='A')
    args = p.parse_args()

    tool = XBeeBenchmark(port=args.port, baudrate=args.baudrate, mode=args.mode, node_id=args.node_id)
    print(f"Starting: port={args.port} baud={args.baudrate} mode={args.mode} node={args.node_id}")
    try:
        tool.start()
    except Exception as e:
        print(f"Fatal: {e}")

if __name__ == '__main__':
    main()
