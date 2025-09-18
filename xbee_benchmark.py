#!/usr/bin/env python3
"""
XBee Network Benchmark Tool
============================
A comprehensive tool for benchmarking XBee module performance including:
- Bandwidth measurement (automatic)
- Latency testing with variable data sizes and intervals
- Bidirectional communication support
- Real-time statistics

Usage:
    python xbee_benchmark.py --port COM3 --mode master
    python xbee_benchmark.py --port COM4 --mode slave
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
        self.node_id = node_id
        self.serial_conn = None
        self.running = False
        
        # Statistics
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.start_time = time.time()
        self.latency_measurements = deque(maxlen=1000)
        self.bandwidth_measurements = deque(maxlen=100)
        
        # Test configuration
        self.test_data_sizes = [8, 16, 32, 64, 128, 256, 512, 1024]  # bytes
        self.test_intervals = [0.1, 0.5, 1.0, 2.0]  # seconds
        self.current_test = 0
        
        # Threading
        self.rx_thread = None
        self.tx_thread = None
        self.stats_thread = None
        
        # Message types
        self.MSG_PING = b'PING'
        self.MSG_PONG = b'PONG'
        self.MSG_DATA = b'DATA'
        self.MSG_SYNC = b'SYNC'
        self.MSG_RESULT = b'RSLT'

    def connect(self):
        """Establish serial connection to XBee module"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"Connected to XBee on {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to {self.port}: {e}")
            return False

    def disconnect(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Disconnected from XBee")

    def create_message(self, msg_type, data_size=0, payload=None):
        """Create a standardized message format"""
        timestamp = struct.pack('<d', time.time())
        node_id = self.node_id.encode('ascii')
        msg_type_packed = msg_type
        data_size_packed = struct.pack('<H', data_size)
        
        if payload is None:
            payload = b'X' * data_size
        
        message = b'$$' + msg_type_packed + node_id + timestamp + data_size_packed + payload + b'##'
        return message

    def parse_message(self, data):
        """Parse received message"""
        try:
            if not data.startswith(b'$$') or not data.endswith(b'##'):
                return None
            
            content = data[2:-2]  # Remove markers
            if len(content) < 15:  # Minimum message size
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
            print(f"Error parsing message: {e}")
            return None

    def send_message(self, msg_type, data_size=0, payload=None):
        """Send message through XBee"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False
        
        try:
            message = self.create_message(msg_type, data_size, payload)
            bytes_sent = self.serial_conn.write(message)
            self.tx_bytes += bytes_sent
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    def receive_messages(self):
        """Continuous message reception thread"""
        buffer = b''
        
        while self.running:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer += data
                    self.rx_bytes += len(data)
                    
                    # Process complete messages
                    while b'$$' in buffer and b'##' in buffer:
                        start = buffer.find(b'$$')
                        end = buffer.find(b'##', start)
                        
                        if end != -1:
                            message_data = buffer[start:end+2]
                            buffer = buffer[end+2:]
                            
                            parsed = self.parse_message(message_data)
                            if parsed:
                                self.handle_received_message(parsed)
                        else:
                            break
                else:
                    time.sleep(0.001)  # Small delay to prevent CPU spinning
                    
            except Exception as e:
                print(f"Error in receive thread: {e}")
                time.sleep(0.1)

    def handle_received_message(self, message):
        """Handle received message based on type"""
        msg_type = message['type']
        
        if msg_type == self.MSG_PING:
            # Respond with PONG
            self.send_message(self.MSG_PONG, message['data_size'], message['payload'])
            
        elif msg_type == self.MSG_PONG:
            # Calculate latency
            latency = message['rx_time'] - message['timestamp']
            self.latency_measurements.append(latency * 1000)  # Convert to ms
            
        elif msg_type == self.MSG_DATA:
            # Data reception for bandwidth testing
            pass  # Bandwidth calculated automatically from rx_bytes
            
        elif msg_type == self.MSG_SYNC:
            print(f"Sync received from node {message['node_id']}")
            
        elif msg_type == self.MSG_RESULT:
            # Results from other node
            try:
                results = json.loads(message['payload'].decode('utf-8'))
                print(f"\n=== Results from Node {message['node_id']} ===")
                self.print_results(results)
            except Exception as e:
                print(f"Error parsing results: {e}")

    def run_latency_test(self, data_size, interval, duration=10):
        """Run latency test with specified parameters"""
        print(f"\n--- Latency Test: {data_size} bytes, {interval}s interval ---")
        
        self.latency_measurements.clear()
        start_time = time.time()
        
        while time.time() - start_time < duration and self.running:
            self.send_message(self.MSG_PING, data_size)
            time.sleep(interval)
        
        # Wait a bit for remaining responses
        time.sleep(2)
        
        if self.latency_measurements:
            avg_latency = statistics.mean(self.latency_measurements)
            min_latency = min(self.latency_measurements)
            max_latency = max(self.latency_measurements)
            
            print(f"Data Size: {data_size} bytes")
            print(f"Packets sent: {len(self.latency_measurements)}")
            print(f"Average Latency: {avg_latency:.2f} ms")
            print(f"Min Latency: {min_latency:.2f} ms")
            print(f"Max Latency: {max_latency:.2f} ms")
            
            return {
                'data_size': data_size,
                'interval': interval,
                'avg_latency': avg_latency,
                'min_latency': min_latency,
                'max_latency': max_latency,
                'packets': len(self.latency_measurements)
            }
        else:
            print("No latency measurements recorded!")
            return None

    def run_bandwidth_test(self, duration=30):
        """Run bandwidth test"""
        print(f"\n--- Bandwidth Test: {duration}s duration ---")
        
        start_bytes = self.tx_bytes
        start_time = time.time()
        
        # Send continuous data
        data_size = 512  # Optimal size for XBee
        
        while time.time() - start_time < duration and self.running:
            self.send_message(self.MSG_DATA, data_size)
            time.sleep(0.01)  # Small delay to prevent overwhelming
        
        end_time = time.time()
        bytes_sent = self.tx_bytes - start_bytes
        elapsed_time = end_time - start_time
        
        bandwidth_bps = bytes_sent / elapsed_time
        bandwidth_kbps = bandwidth_bps / 1024
        
        print(f"Bytes sent: {bytes_sent}")
        print(f"Time elapsed: {elapsed_time:.2f} seconds")
        print(f"Bandwidth: {bandwidth_bps:.2f} bytes/sec ({bandwidth_kbps:.2f} KB/s)")
        
        return {
            'duration': elapsed_time,
            'bytes_sent': bytes_sent,
            'bandwidth_bps': bandwidth_bps,
            'bandwidth_kbps': bandwidth_kbps
        }

    def calculate_rx_bandwidth(self):
        """Calculate receive bandwidth"""
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        if elapsed > 0:
            rx_bandwidth_bps = self.rx_bytes / elapsed
            rx_bandwidth_kbps = rx_bandwidth_bps / 1024
            return rx_bandwidth_bps, rx_bandwidth_kbps
        return 0, 0

    def print_statistics(self):
        """Print real-time statistics"""
        while self.running:
            time.sleep(5)  # Update every 5 seconds
            
            rx_bps, rx_kbps = self.calculate_rx_bandwidth()
            current_time = datetime.now().strftime("%H:%M:%S")
            
            print(f"\n[{current_time}] === Statistics ===")
            print(f"TX Bytes: {self.tx_bytes}")
            print(f"RX Bytes: {self.rx_bytes}")
            print(f"RX Bandwidth: {rx_bps:.2f} bytes/sec ({rx_kbps:.2f} KB/s)")
            
            if self.latency_measurements:
                recent_latency = list(self.latency_measurements)[-10:]  # Last 10 measurements
                avg_recent_latency = statistics.mean(recent_latency)
                print(f"Recent Avg Latency: {avg_recent_latency:.2f} ms")

    def run_comprehensive_test(self):
        """Run comprehensive benchmark tests"""
        print(f"\n=== XBee Benchmark - Node {self.node_id} ({self.mode} mode) ===")
        
        # Wait for connection stabilization
        time.sleep(2)
        
        results = {
            'node_id': self.node_id,
            'mode': self.mode,
            'timestamp': datetime.now().isoformat(),
            'latency_tests': [],
            'bandwidth_test': None
        }
        
        if self.mode == 'master':
            print("\nStarting as MASTER node...")
            
            # Send sync message
            self.send_message(self.MSG_SYNC, 0)
            time.sleep(1)
            
            # Run latency tests with different parameters
            for data_size in self.test_data_sizes[:4]:  # Test first 4 sizes
                for interval in self.test_intervals[:2]:  # Test first 2 intervals
                    if not self.running:
                        break
                    
                    latency_result = self.run_latency_test(data_size, interval, duration=15)
                    if latency_result:
                        results['latency_tests'].append(latency_result)
                    
                    time.sleep(2)  # Pause between tests
            
            # Run bandwidth test
            bandwidth_result = self.run_bandwidth_test(duration=20)
            results['bandwidth_test'] = bandwidth_result
            
            # Send results to other node
            results_json = json.dumps(results, indent=2)
            self.send_message(self.MSG_RESULT, len(results_json), results_json.encode('utf-8'))
            
        else:
            print("\nStarting as SLAVE node...")
            print("Waiting for master node to initiate tests...")
            
            # In slave mode, just respond to incoming messages
            # The receive thread handles PING->PONG automatically
            
            # Run a shorter bandwidth test
            time.sleep(30)  # Wait for master to finish
            bandwidth_result = self.run_bandwidth_test(duration=10)
            results['bandwidth_test'] = bandwidth_result
        
        return results

    def print_results(self, results):
        """Print formatted test results"""
        print(f"Node ID: {results['node_id']}")
        print(f"Mode: {results['mode']}")
        print(f"Timestamp: {results['timestamp']}")
        
        if results['latency_tests']:
            print(f"\n--- Latency Test Results ---")
            for test in results['latency_tests']:
                print(f"Data Size: {test['data_size']} bytes, "
                      f"Interval: {test['interval']}s, "
                      f"Avg Latency: {test['avg_latency']:.2f} ms")
        
        if results['bandwidth_test']:
            bw = results['bandwidth_test']
            print(f"\n--- Bandwidth Test Results ---")
            print(f"Duration: {bw['duration']:.2f} seconds")
            print(f"Bytes Sent: {bw['bytes_sent']}")
            print(f"Bandwidth: {bw['bandwidth_kbps']:.2f} KB/s")

    def start(self):
        """Start the benchmark tool"""
        if not self.connect():
            return False
        
        self.running = True
        
        # Start threads
        self.rx_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.stats_thread = threading.Thread(target=self.print_statistics, daemon=True)
        
        self.rx_thread.start()
        self.stats_thread.start()
        
        try:
            # Run tests
            results = self.run_comprehensive_test()
            
            # Print final results
            print("\n" + "="*50)
            print("FINAL RESULTS")
            print("="*50)
            self.print_results(results)
            
            # Keep running to receive results from other node
            if self.mode == 'slave':
                print("\nWaiting for results from master node...")
                time.sleep(10)
            
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.running = False
            self.disconnect()

def main():
    parser = argparse.ArgumentParser(description='XBee Network Benchmark Tool')
    parser.add_argument('--port', '-p', required=True, help='COM port (e.g., COM3, /dev/ttyUSB0)')
    parser.add_argument('--baudrate', '-b', type=int, default=9600, help='Baud rate (default: 9600)')
    parser.add_argument('--mode', '-m', choices=['master', 'slave'], default='master', 
                       help='Operation mode (default: master)')
    parser.add_argument('--node-id', '-n', default='A', help='Node identifier (default: A)')
    
    args = parser.parse_args()
    
    # Create and start benchmark tool
    benchmark = XBeeBenchmark(
        port=args.port,
        baudrate=args.baudrate,
        mode=args.mode,
        node_id=args.node_id
    )
    
    print(f"Starting XBee Benchmark Tool...")
    print(f"Port: {args.port}")
    print(f"Baudrate: {args.baudrate}")
    print(f"Mode: {args.mode}")
    print(f"Node ID: {args.node_id}")
    print("\nPress Ctrl+C to stop")
    
    benchmark.start()

if __name__ == "__main__":
    main()