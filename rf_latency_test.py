#!/usr/bin/env python3
"""
RF Communication Bandwidth Testing Script (improved pacing)

This version adds pacing and chunked writes so larger packets (e.g. 512, 1024 bytes)
are not sent too fast for half-duplex RF modules that have small internal buffers.

Key changes:
 - chunked_send(): splits payload into small chunks (default 256 bytes) and inserts
   a small delay between chunks so the radio's TX buffer/airlink won't drop data.
 - estimate_tx_time(): calculates theoretical on-air time using baudrate and a
   small guard time. We wait at least this long (plus a margin) after the final
   write before expecting an ACK — avoids premature timeouts.
 - receive timeout is dynamic and scaled with estimated on-air time.
 - improved logging for pacing decisions and retries.

Usage same as earlier: run on base and rover with --mode and --port.
"""

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from typing import Dict, List, Tuple

import serial


CHUNK_SIZE = 256  # bytes per write chunk (tune for your radio)
CHUNK_GAP_S = 0.002  # small gap between chunks (2 ms)
ACK_BYTES = b"ACK"


class RFBandwidthTester:
    def __init__(self, port: str, baudrate: int = 115200, mode: str = "base", debug: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.mode = mode
        self.debug = debug
        self.ser: serial.Serial | None = None
        self.test_sizes = [64, 128, 256, 512, 1024]
        self.iterations = 10
        self.timeout = 5.0

    def connect(self) -> bool:
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.01,  # low-level read timeout
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
            )
            print(f"Connected to {self.port} at {self.baudrate} baud")
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"Failed to open serial port {self.port}: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial port closed")

    def get_gps(self) -> Dict[str, str]:
        return {"latitude": "0.000000", "longitude": "0.000000", "altitude": "0.0"}

    def generate_test_data(self, size: int) -> bytes:
        pattern = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        data = (pattern * ((size // len(pattern)) + 1))[:size]
        return data

    def estimate_tx_time(self, size: int) -> float:
        """Estimate on-air transmission time in seconds for `size` bytes at configured baudrate."""
        bits = size * 8
        # Include one start + one stop bit per byte (approx) -> 10 bits/byte common estimate
        bits_with_framing = size * 10
        tx_time = bits_with_framing / float(self.baudrate)
        # add small guard margin
        return tx_time + 0.001

    def send_data(self, data: bytes) -> int:
        try:
            if not self.ser or not self.ser.is_open:
                return -1
            written = self.ser.write(data)
            self.ser.flush()
            return written
        except Exception as e:
            if self.debug:
                print(f"send_data error: {e}")
            return -1

    def chunked_send(self, data: bytes, chunk_size: int = CHUNK_SIZE, gap_s: float = CHUNK_GAP_S) -> int:
        """Send data in chunks with small gap between chunks. Returns total bytes written."""
        total_written = 0
        idx = 0
        try:
            while idx < len(data):
                end = min(idx + chunk_size, len(data))
                chunk = data[idx:end]
                written = self.send_data(chunk)
                if written <= 0:
                    if self.debug:
                        print(f"chunked_send: wrote {written} bytes for chunk idx {idx}")
                    break
                total_written += written
                idx = end
                # small gap to avoid overflowing TX buffer on some radios
                time.sleep(gap_s)
            return total_written
        except Exception as e:
            if self.debug:
                print(f"chunked_send error: {e}")
            return total_written

    def receive_data_with_timeout(self, expected_size: int, timeout: float = 5.0) -> Tuple[bytes, int, int]:
        if not self.ser or not self.ser.is_open:
            return b"", 0, 0

        start_ns = time.time_ns()
        deadline_ns = start_ns + int(timeout * 1_000_000_000)
        received = bytearray()
        last_recv_ts = 0

        try:
            while time.time_ns() < deadline_ns and len(received) < expected_size:
                to_read = min(expected_size - len(received), 4096)
                chunk = self.ser.read(to_read)
                if chunk:
                    received.extend(chunk)
                    last_recv_ts = time.time_ns()
                else:
                    time.sleep(0.001)

            if len(received) == 0:
                return bytes(received), 0, 0

            elapsed_ns = last_recv_ts - start_ns if last_recv_ts else 0
            return bytes(received), int(elapsed_ns), int(last_recv_ts)
        except Exception as e:
            if self.debug:
                print(f"receive_data_with_timeout error: {e}")
            return b"", 0, 0

    def wait_for_sync(self) -> bool:
        sync_msg = b"SYNC_READY"
        if not self.ser or not self.ser.is_open:
            return False
        try:
            if self.mode == "base":
                print("Base: sending sync...")
                self.ser.reset_input_buffer()
                self.ser.write(sync_msg)
                self.ser.flush()
                received, _, _ = self.receive_data_with_timeout(len(sync_msg), timeout=5.0)
                if received == sync_msg:
                    print("Sync established")
                    return True
                print("Sync not received (base)")
                return False
            else:
                print("Rover: waiting for sync...")
                received, _, _ = self.receive_data_with_timeout(len(sync_msg), timeout=30.0)
                if received == sync_msg:
                    print("Rover: received sync, echoing")
                    self.ser.write(sync_msg)
                    self.ser.flush()
                    return True
                print("Rover: no sync")
                return False
        except Exception as e:
            if self.debug:
                print(f"wait_for_sync error: {e}")
            return False

    def test_as_base(self) -> Dict:
        results: Dict[str, Dict] = {}

        for size in self.test_sizes:
            print(f"\n--- Testing size: {size} bytes ---")
            latencies_ms: List[float] = []
            bandwidths_kbps: List[float] = []

            for it in range(self.iterations):
                if self.ser and self.ser.in_waiting:
                    self.ser.reset_input_buffer()

                # send 4-byte size header
                size_bytes = size.to_bytes(4, "big")
                if self.send_data(size_bytes) != 4:
                    print("Failed to send size header")
                    time.sleep(0.1)
                    continue

                # tiny guard to let header be processed on rover
                time.sleep(0.02)

                test_data = self.generate_test_data(size)

                # estimate on-air time and set dynamic timeouts
                est_tx_s = self.estimate_tx_time(size)
                ack_wait_timeout = max(0.5, est_tx_s * 3 + 0.2)

                if self.debug:
                    print(f"Estimated TX time: {est_tx_s*1000:.3f} ms, ACK timeout: {ack_wait_timeout:.3f} s")

                # start time just before we start chunked send
                tx_start_ns = time.time_ns()
                bytes_written = self.chunked_send(test_data)
                tx_end_ns = time.time_ns()

                if bytes_written != size:
                    print(f"Warning: wrote {bytes_written}/{size} bytes")

                # Wait at least the estimated on-air time plus a small margin
                wait_for_processing = max(0.005, est_tx_s + 0.005)
                if self.debug:
                    print(f"Waiting {wait_for_processing*1000:.3f} ms for on-air + processing margin")
                time.sleep(wait_for_processing)

                # now wait for ACK with dynamic timeout
                ack, ack_elapsed_ns, ack_last_ts = self.receive_data_with_timeout(len(ACK_BYTES), timeout=ack_wait_timeout)

                if ack == ACK_BYTES and ack_last_ts:
                    rtt_ns = ack_last_ts - tx_start_ns
                    if rtt_ns <= 0:
                        rtt_ns = max(1, tx_end_ns - tx_start_ns) * 2

                    one_way_ns = rtt_ns / 2.0
                    latency_ms = one_way_ns / 1_000_000.0
                    one_way_s = one_way_ns / 1_000_000_000.0

                    measured_bps = (size / one_way_s) if one_way_s > 0 else 0.0
                    measured_kBps = measured_bps / 1024.0

                    latencies_ms.append(latency_ms)
                    bandwidths_kbps.append(measured_kBps)

                    print(f"Iter {it+1}: Latency {latency_ms:.3f} ms, BW {measured_kBps:.2f} KB/s")
                else:
                    print(f"Iter {it+1}: No ACK or timeout (got: {ack})")

                # Running 1Mbps radios can get overwhelmed if we send too fast
                # small delay between iterations
                time.sleep(2 * bytes_written / 1000 + 0.1)

            # aggregate
            if latencies_ms:
                avg_latency = statistics.mean(latencies_ms)
                avg_bw = statistics.mean(bandwidths_kbps)
                results[str(size)] = {
                    "latency": f"{avg_latency:.3f} ms",
                    "bandwidth": f"{avg_bw:.2f} KB/s",
                    "measurements": {
                        "samples": len(latencies_ms),
                        "latencies_ms": [f"{v:.3f}" for v in latencies_ms],
                        "bandwidths_kBps": [f"{v:.2f}" for v in bandwidths_kbps],
                    },
                }
                print(f"-> {size} bytes: avg latency {avg_latency:.3f} ms, avg BW {avg_bw:.2f} KB/s")
            else:
                results[str(size)] = {"latency": None, "bandwidth": None, "measurements": {"samples": 0}}
                print(f"-> {size} bytes: no successful samples")

        return results

    def test_as_rover(self):
        print("Rover: receiver loop started")
        try:
            while True:
                size_data, _, _ = self.receive_data_with_timeout(4, timeout=30.0)
                if len(size_data) != 4:
                    continue

                expected_size = int.from_bytes(size_data, "big")
                if self.debug:
                    print(f"Rover: expecting {expected_size} bytes")

                # set receive timeout proportional to expected_size
                timeout_for_payload = max(1.0, self.estimate_tx_time(expected_size) * 3 + 0.5)
                payload, payload_elapsed_ns, payload_last_ts = self.receive_data_with_timeout(expected_size, timeout=timeout_for_payload)

                if len(payload) == expected_size:
                    # small pause to ensure half-duplex radio is ready to transmit
                    time.sleep(0.005)
                    # send ACK
                    self.send_data(ACK_BYTES)
                    if self.debug:
                        print(f"Rover: received {len(payload)} bytes, sent ACK")
                else:
                    if self.debug:
                        print(f"Rover: incomplete payload {len(payload)}/{expected_size}")

        except KeyboardInterrupt:
            print("Rover: interrupted by user")

    def save_results(self, results: Dict[str, Dict], gps_data: Dict[str, str]):
        timestamp_ns = time.time_ns()
        timestamp_iso = datetime.now().isoformat()

        entry = {
            "timestamp": timestamp_iso,
            "timestamp_ns": timestamp_ns,
            "location": {
                "base_coordinate": f"{gps_data['latitude']},{gps_data['longitude']}",
                "rover_coordinate": "0.000000,0.000000",
            },
        }

        entry.update(results)

        out_file = "output.json"
        if os.path.exists(out_file):
            try:
                with open(out_file, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {"data": []}
        else:
            data = {"data": []}

        data["data"].append(entry)

        with open(out_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Saved results to {out_file}")

    def run_test(self) -> bool:
        if not self.connect():
            return False

        try:
            if not self.wait_for_sync():
                print("Failed to synchronize with peer")
                return False

            gps = self.get_gps()

            if self.mode == "base":
                print("Starting tests (base)")
                res = self.test_as_base()
                self.save_results(res, gps)
                return True
            else:
                print("Starting rover receiver")
                self.test_as_rover()
                return True

        except KeyboardInterrupt:
            print("Test interrupted")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.disconnect()

        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "rover"], required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    tester = RFBandwidthTester(args.port, args.baudrate, args.mode, args.debug)
    success = tester.run_test()
    if success:
        print("Done")
    else:
        print("Exited with errors or aborted")


if __name__ == "__main__":
    main()
