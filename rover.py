import serial
import time
import json
import multiprocessing
from multiprocessing import Process, Queue
import queue

# Hardcoded configuration
transmission_interval = 1
data_size = 100
port = "COM10"
baud = 57600

def transmission_process(tx_queue, port, baud):
    """Handle outgoing transmissions"""
    ser_tx = serial.Serial(port, baud, timeout=1)
    print("[Rover TX] Transmission process started")
    
    while True:
        try:
            # Get message from queue with timeout
            message = tx_queue.get(timeout=0.1)
            if message == "STOP":
                break
            
            ser_tx.write(message.encode("utf-8"))
            print(f"[Rover TX] Sent: {message[:50]}...")  # Show first 50 chars
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Rover TX] Error: {e}")
    
    ser_tx.close()
    print("[Rover TX] Transmission process stopped")

def reception_process(rx_queue, port, baud):
    """Handle incoming receptions"""
    ser_rx = serial.Serial(port, baud, timeout=1)
    print("[Rover RX] Reception process started")
    
    while True:
        try:
            # Check for stop signal
            try:
                stop_signal = rx_queue.get_nowait()
                if stop_signal == "STOP":
                    break
            except queue.Empty:
                pass
            
            # Read incoming data
            if ser_rx.in_waiting > 0:
                data = ser_rx.readline().decode("utf-8").strip()
                if data:
                    print(f"[Rover RX] Received: {data[:50]}...")  # Show first 50 chars
                    
                    # Process the received message
                    try:
                        parts = data.split("$")
                        if len(parts) >= 3:
                            msg_id = parts[0]
                            sent_time = int(parts[1])
                            payload = parts[2]
                            recv_time = time.time_ns()
                            
                            # Calculate delay
                            delay = (recv_time - sent_time) / 1_000_000_000  # Convert to seconds
                            
                            # Prepare response with receive timestamp
                            response = f"{msg_id}${sent_time}${recv_time}"
                            
                            # Send response back
                            ser_rx.write(response.encode("utf-8"))
                            print(f"[Rover RX] Message {msg_id} Delay {delay:.6f} seconds")
                            
                    except Exception as e:
                        print(f"[Rover RX] Error processing message: {e}")
            
            time.sleep(0.01)  # Small delay to prevent excessive CPU usage
            
        except Exception as e:
            print(f"[Rover RX] Error: {e}")
            time.sleep(0.1)
    
    ser_rx.close()
    print("[Rover RX] Reception process stopped")

def main():
    """Main function to start both processes"""
    # Create queues for inter-process communication
    tx_queue = Queue()
    rx_queue = Queue()
    
    # Create and start processes
    tx_process = Process(target=transmission_process, args=(tx_queue, port, baud))
    rx_process = Process(target=reception_process, args=(rx_queue, port, baud))
    
    tx_process.start()
    rx_process.start()
    
    print("[Rover Main] Both processes started")
    
    try:
        # Main loop - you can add control logic here
        while True:
            # Example: Send a test message every 10 seconds
            time.sleep(10)
            test_msg = f"TEST${time.time_ns()}$Hello from rover"
            tx_queue.put(test_msg)
            
    except KeyboardInterrupt:
        print("\n[Rover Main] Shutting down...")
        
        # Stop both processes
        tx_queue.put("STOP")
        rx_queue.put("STOP")
        
        # Wait for processes to finish
        tx_process.join(timeout=5)
        rx_process.join(timeout=5)
        
        # Force terminate if still running
        if tx_process.is_alive():
            tx_process.terminate()
        if rx_process.is_alive():
            rx_process.terminate()
        
        print("[Rover Main] Shutdown complete")

if __name__ == "__main__":
    main()