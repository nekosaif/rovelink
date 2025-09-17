#!/usr/bin/env python3
"""
COM Port Throughput and Latency Tester

This application tests serial communication performance by measuring:
- Throughput (bytes per second)
- Latency (round-trip time)
- Packet loss/errors

Requirements:
    pip install pyserial

Usage:
    python com_port_tester.py
"""

import serial
import serial.tools.list_ports
import time
import threading
import statistics
import sys
from datetime import datetime
import argparse


class COMPortTester:
    def __init__(self, port, baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.running = False
        
    def connect(self):
        """Establish connection to COM port"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"✓ Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"✗ Failed to connect to {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print(f"✓ Disconnected from {self.port}")
    
    def test_latency(self, num_tests=10, packet_size=64):
        """Test round-trip latency"""
        print(f"\n--- Latency Test ---")
        print(f"Sending {num_tests} packets of {packet_size} bytes each")
        
        if not self.serial_conn or not self.serial_conn.is_open:
            print("✗ Serial connection not established")
            return None
    
    def test_throughput_device(self, duration=10):
        """Test throughput with a connected device (not loopback)"""
        print(f"\n--- Device Throughput Test ---")
        print(f"Measuring data exchange with device for {duration} seconds")
        
        if not self.serial_conn or not self.serial_conn.is_open:
            print("✗ Serial connection not established")
            return None
        
        bytes_sent = 0
        bytes_received = 0
        messages_sent = 0
        start_time = time.time()
        
        # Start receiver thread
        self.running = True
        received_data = []
        
        def receiver():
            while self.running:
                try:
                    data = self.serial_conn.read(1024)
                    if data:
                        received_data.append(data)
                except:
                    break
        
        receiver_thread = threading.Thread(target=receiver)
        receiver_thread.daemon = True
        receiver_thread.start()
        
        # Send commands/data continuously
        try:
            message_counter = 0
            while time.time() - start_time < duration:
                # Send a command or data packet
                message = f"DATA{message_counter:06d}\n".encode()
                self.serial_conn.write(message)
                bytes_sent += len(message)
                messages_sent += 1
                message_counter += 1
                
                # Small delay to prevent overwhelming the device
                time.sleep(0.05)  # 50ms between messages
                
        except KeyboardInterrupt:
            print("\nTest interrupted by user")
        except Exception as e:
            print(f"Error during device throughput test: {e}")
        
        # Stop receiver
        self.running = False
        time.sleep(0.2)  # Allow receiver to finish
        
        end_time = time.time()
        actual_duration = end_time - start_time
        
        # Calculate received bytes
        for data in received_data:
            bytes_received += len(data)
        
        # Calculate throughput
        if actual_duration > 0:
            tx_throughput_bps = bytes_sent / actual_duration
            rx_throughput_bps = bytes_received / actual_duration
            message_rate = messages_sent / actual_duration
            
            print(f"\n--- Device Throughput Results ---")
            print(f"Test Duration: {actual_duration:.2f} seconds")
            print(f"Messages Sent: {messages_sent}")
            print(f"Message Rate: {message_rate:.1f} messages/sec")
            print(f"Bytes Sent: {bytes_sent:,}")
            print(f"Bytes Received: {bytes_received:,}")
            print(f"TX Rate: {tx_throughput_bps:.0f} bytes/sec ({tx_throughput_bps*8:.0f} bits/sec)")
            print(f"RX Rate: {rx_throughput_bps:.0f} bytes/sec ({rx_throughput_bps*8:.0f} bits/sec)")
            
            if bytes_sent > 0:
                response_ratio = bytes_received / bytes_sent
                print(f"Response Ratio: {response_ratio:.2f} (RX/TX)")
            
            # Show sample received data
            if received_data:
                print(f"Sample received data:")
                for i, data in enumerate(received_data[:3]):
                    print(f"  Chunk {i+1}: {data[:100]}...")  # First 100 bytes
            
            return {
                'tx_throughput_bps': tx_throughput_bps,
                'rx_throughput_bps': rx_throughput_bps,
                'bytes_sent': bytes_sent,
                'bytes_received': bytes_received,
                'message_rate': message_rate,
                'duration': actual_duration,
                'response_ratio': bytes_received / bytes_sent if bytes_sent > 0 else 0
            }
        
        return None
        
        latencies = []
        errors = 0
        
        # Create test packet
        test_data = b'A' * (packet_size - 1) + b'\n'
        
        for i in range(num_tests):
            try:
                # Clear input buffer
                self.serial_conn.reset_input_buffer()
                
                # Send packet and measure time
                start_time = time.time()
                self.serial_conn.write(test_data)
                
                # Wait for echo/response
                response = self.serial_conn.readline()
                end_time = time.time()
                
                if response:
                    latency_ms = (end_time - start_time) * 1000
                    latencies.append(latency_ms)
                    print(f"Packet {i+1}: {latency_ms:.2f} ms")
                else:
                    errors += 1
                    print(f"Packet {i+1}: TIMEOUT")
                
                time.sleep(0.1)  # Small delay between tests
                
            except Exception as e:
                errors += 1
                print(f"Packet {i+1}: ERROR - {e}")
        
        # Calculate statistics
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
            
            print(f"\n--- Latency Results ---")
            print(f"Average: {avg_latency:.2f} ms")
            print(f"Minimum: {min_latency:.2f} ms")
            print(f"Maximum: {max_latency:.2f} ms")
            print(f"Jitter (StdDev): {jitter:.2f} ms")
            print(f"Success Rate: {len(latencies)}/{num_tests} ({len(latencies)/num_tests*100:.1f}%)")
            
            return {
                'average': avg_latency,
                'min': min_latency,
                'max': max_latency,
                'jitter': jitter,
                'success_rate': len(latencies)/num_tests
            }
        else:
            print("✗ No successful latency measurements")
            return None
    
    def test_throughput(self, duration=10, packet_size=1024):
        """Test throughput by sending continuous data"""
        print(f"\n--- Throughput Test ---")
        print(f"Sending data for {duration} seconds with {packet_size} byte packets")
        
        if not self.serial_conn or not self.serial_conn.is_open:
            print("✗ Serial connection not established")
            return None
        
        # Create test packet
        test_data = b'X' * packet_size
        
        bytes_sent = 0
        bytes_received = 0
        packets_sent = 0
        start_time = time.time()
        
        # Start receiver thread
        self.running = True
        received_bytes = [0]  # Use list for mutable reference
        
        def receiver():
            while self.running:
                try:
                    data = self.serial_conn.read(packet_size)
                    received_bytes[0] += len(data)
                except:
                    break
        
        receiver_thread = threading.Thread(target=receiver)
        receiver_thread.daemon = True
        receiver_thread.start()
        
        # Send data continuously
        try:
            while time.time() - start_time < duration:
                self.serial_conn.write(test_data)
                bytes_sent += len(test_data)
                packets_sent += 1
                
                # Small delay to prevent overwhelming
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            print("\nTest interrupted by user")
        except Exception as e:
            print(f"Error during throughput test: {e}")
        
        # Stop receiver
        self.running = False
        time.sleep(0.1)  # Allow receiver to finish
        
        end_time = time.time()
        actual_duration = end_time - start_time
        bytes_received = received_bytes[0]
        
        # Calculate throughput
        if actual_duration > 0:
            tx_throughput_bps = bytes_sent / actual_duration
            rx_throughput_bps = bytes_received / actual_duration
            
            print(f"\n--- Throughput Results ---")
            print(f"Test Duration: {actual_duration:.2f} seconds")
            print(f"Packets Sent: {packets_sent}")
            print(f"Bytes Sent: {bytes_sent:,}")
            print(f"Bytes Received: {bytes_received:,}")
            print(f"TX Throughput: {tx_throughput_bps:.0f} bytes/sec ({tx_throughput_bps*8:.0f} bits/sec)")
            print(f"RX Throughput: {rx_throughput_bps:.0f} bytes/sec ({rx_throughput_bps*8:.0f} bits/sec)")
            print(f"Data Loss: {((bytes_sent - bytes_received) / bytes_sent * 100):.2f}%")
            
            return {
                'tx_throughput_bps': tx_throughput_bps,
                'rx_throughput_bps': rx_throughput_bps,
                'bytes_sent': bytes_sent,
                'bytes_received': bytes_received,
                'duration': actual_duration,
                'data_loss_percent': (bytes_sent - bytes_received) / bytes_sent * 100
            }
        
        return None
    
    def loopback_test(self):
        """Test if loopback is working (TX connected to RX)"""
        print(f"\n--- Loopback Test ---")
        
        if not self.serial_conn or not self.serial_conn.is_open:
            print("✗ Serial connection not established")
            return False
        
        test_message = b"LOOPBACK_TEST_123\n"
        
        try:
            self.serial_conn.reset_input_buffer()
            self.serial_conn.write(test_message)
            time.sleep(0.1)
            
            response = self.serial_conn.readline()
            
            if response == test_message:
                print("✓ Perfect loopback detected")
                return True
            elif response:
                print(f"✓ Device responding - Received: {response}")
                print("  This appears to be a device that modifies or generates data")
                
                # Ask user if they want to continue with device testing
                try:
                    user_input = input("Continue with device communication tests? (y/n): ").strip().lower()
                    return user_input in ['y', 'yes']
                except KeyboardInterrupt:
                    return False
            else:
                print("✗ No response from device")
                return False
                
        except Exception as e:
            print(f"✗ Loopback test ERROR: {e}")
            return False

    def device_communication_test(self, num_tests=10):
        """Test communication with a device (not perfect loopback)"""
        print(f"\n--- Device Communication Test ---")
        print(f"Testing communication latency with connected device")
        
        if not self.serial_conn or not self.serial_conn.is_open:
            print("✗ Serial connection not established")
            return None
        
        latencies = []
        responses = []
        errors = 0
        
        for i in range(num_tests):
            try:
                # Clear input buffer
                self.serial_conn.reset_input_buffer()
                
                # Send a simple command and measure response time
                test_command = f"TEST{i:03d}\n".encode()
                start_time = time.time()
                self.serial_conn.write(test_command)
                
                # Wait for any response
                response = self.serial_conn.read(1024)  # Read up to 1024 bytes
                end_time = time.time()
                
                if response:
                    latency_ms = (end_time - start_time) * 1000
                    latencies.append(latency_ms)
                    responses.append(response)
                    print(f"Command {i+1}: {latency_ms:.2f} ms - Got {len(response)} bytes")
                else:
                    errors += 1
                    print(f"Command {i+1}: TIMEOUT")
                
                time.sleep(0.2)  # Delay between commands
                
            except Exception as e:
                errors += 1
                print(f"Command {i+1}: ERROR - {e}")
        
        # Show some sample responses
        if responses:
            print(f"\nSample responses:")
            for i, resp in enumerate(responses[:3]):
                print(f"  Response {i+1}: {resp}")
        
        # Calculate statistics
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
            
            print(f"\n--- Device Communication Results ---")
            print(f"Average Response Time: {avg_latency:.2f} ms")
            print(f"Minimum Response Time: {min_latency:.2f} ms")
            print(f"Maximum Response Time: {max_latency:.2f} ms")
            print(f"Jitter (StdDev): {jitter:.2f} ms")
            print(f"Success Rate: {len(latencies)}/{num_tests} ({len(latencies)/num_tests*100:.1f}%)")
            
            return {
                'average': avg_latency,
                'min': min_latency,
                'max': max_latency,
                'jitter': jitter,
                'success_rate': len(latencies)/num_tests
            }
        else:
            print("✗ No successful communications")
            return None


def list_com_ports():
    """List available COM ports"""
    ports = serial.tools.list_ports.comports()
    if ports:
        print("Available COM ports:")
        for port in ports:
            print(f"  {port.device} - {port.description}")
    else:
        print("No COM ports found")
    return [port.device for port in ports]


def main():
    parser = argparse.ArgumentParser(description='COM Port Throughput and Latency Tester')
    parser.add_argument('--port', '-p', help='COM port (e.g., COM1, /dev/ttyUSB0)')
    parser.add_argument('--baudrate', '-b', type=int, default=57600, help='Baud rate (default: 9600)')
    parser.add_argument('--timeout', '-t', type=float, default=10, help='Timeout in seconds (default: 1.0)')
    parser.add_argument('--list-ports', '-l', action='store_true', help='List available COM ports')
    
    args = parser.parse_args()
    
    if args.list_ports:
        list_com_ports()
        return
    
    # If no port specified, list available ports and ask user
    if not args.port:
        available_ports = list_com_ports()
        if not available_ports:
            print("No COM ports available")
            return
        
        print("\nEnter COM port to test:")
        port = input().strip()
        if not port:
            print("No port specified")
            return
    else:
        port = args.port
    
    print(f"\n{'='*50}")
    print(f"COM Port Performance Tester")
    print(f"{'='*50}")
    print(f"Port: {port}")
    print(f"Baudrate: {args.baudrate}")
    print(f"Timeout: {args.timeout}s")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create tester instance
    tester = COMPortTester(port, args.baudrate, args.timeout)
    
    try:
        # Connect to port
        if not tester.connect():
            return
        
        # Run tests
        print(f"\nNote: For throughput testing, ensure TX and RX are connected (loopback)")
        print("Press Ctrl+C to interrupt tests")
        
        # Test loopback first
        loopback_ok = tester.loopback_test()
        
        if loopback_ok:
            # Run latency test
            tester.test_latency(num_tests=20, packet_size=64)
            
            # Run throughput test
            tester.test_throughput(duration=5, packet_size=1024)
        else:
            print("\nRunning device communication tests instead...")
            
            # Test device communication
            tester.device_communication_test(num_tests=15)
            
            # Test device throughput
            tester.test_throughput_device(duration=5)
        
        print(f"\n{'='*50}")
        print("Testing completed")
        
    except KeyboardInterrupt:
        print("\nTesting interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        tester.disconnect()


if __name__ == "__main__":
    main()