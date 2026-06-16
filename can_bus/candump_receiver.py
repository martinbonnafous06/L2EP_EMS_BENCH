import subprocess
import re
import argparse
import sys
import json
import socket
import os
import threading

FILE_LOCK = threading.Lock()

def send_to_node(message, uds_path="/tmp/p2p_node.sock"):
    """Sends parsed CAN data to the local P2P node via Unix Domain Socket."""
    if not os.path.exists(uds_path):
        return False
    try:
        if not hasattr(socket, 'AF_UNIX'):
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(uds_path)
            payload_dict = {
                "target": "all",
                "content": message
            }
            client.sendall(json.dumps(payload_dict).encode())
            return True
    except Exception as e:
        print(f"[!] UDS send error: {e}", file=sys.stderr)
        return False

class CandumpReceiver(threading.Thread):
    def __init__(self, interface, forward_uds=False, uds_path="/tmp/p2p_node.sock", output_file=None, send_interval=10.0):
        super().__init__()
        self.interface = interface
        self.forward_uds = forward_uds
        self.uds_path = uds_path
        self.output_file = output_file
        self.send_interval = float(send_interval)
        self.running = False
        self.process = None
        self.daemon = True
        
        # Buffer for merging CAN frames
        self.buffer = {}
        self.buffer_lock = threading.Lock()
        self.buffer_thread = None

    def run(self):
        self.running = True
        
        # Start buffer sender thread if interval is greater than 0
        if self.send_interval > 0:
            self.buffer_thread = threading.Thread(target=self.send_buffer_loop, daemon=True)
            self.buffer_thread.start()
            
        print(f"[*] Starting candump receiver thread on interface '{self.interface}'...")
        if self.send_interval > 0:
            print(f"[*] Merged CAN data will be sent every {self.send_interval} seconds.")
        else:
            print("[*] CAN frames will be sent immediately.")
        
        try:
            # -L outputs log format: (1612345678.123456) can0 123#1122334455667788
            self.process = subprocess.Popen(
                ['candump', '-L', self.interface],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
        except FileNotFoundError:
            print("[!] Error: 'candump' command not found. Is can-utils installed?", file=sys.stderr)
            print("    Try running: sudo apt-get install can-utils", file=sys.stderr)
            self.running = False
            return

        # Regex to parse the candump -L format
        log_pattern = re.compile(r"\((\d+\.\d+)\)\s+(\S+)\s+([\da-fA-F]+)#([\da-fA-F]*)")

        try:
            for line in self.process.stdout:
                if not self.running:
                    break
                line = line.strip()
                if not line:
                    continue

                match = log_pattern.search(line)
                if match:
                    timestamp, iface, can_id, data = match.groups()
                    frame = {
                        "timestamp": float(timestamp),
                        "interface": iface,
                        "id": can_id,
                        "data": data,
                        "type": "CAN_FRAME"
                    }
                    
                    log_msg = f"[{iface}] ID: {can_id} | Data: {data} | Time: {timestamp}"
                    print(log_msg)
                    
                    # Write to file if an output file was specified (thread-safe merge)
                    if self.output_file:
                        with FILE_LOCK:
                            if self.output_file.endswith('.json'):
                                log_data = []
                                if os.path.exists(self.output_file):
                                    try:
                                        with open(self.output_file, 'r') as f:
                                            log_data = json.load(f)
                                    except Exception:
                                        pass
                                if not isinstance(log_data, list):
                                    log_data = []
                                log_data.append(frame)
                                try:
                                    with open(self.output_file, 'w') as f:
                                        json.dump(log_data, f, indent=4)
                                except Exception as e:
                                    print(f"[!] Error writing JSON log: {e}", file=sys.stderr)
                            else:
                                try:
                                    with open(self.output_file, 'a') as f:
                                        f.write(log_msg + "\n")
                                except Exception as e:
                                    print(f"[!] Error writing text log: {e}", file=sys.stderr)

                    # Store in buffer if send_interval is set, else send immediately
                    if self.send_interval > 0:
                        with self.buffer_lock:
                            self.buffer[can_id] = frame
                    else:
                        if self.forward_uds:
                            send_to_node(frame, self.uds_path)
                else:
                    print(f"[?] Unrecognized format: {line}")
        except Exception as e:
            if self.running:
                print(f"[!] Error in candump receiver loop: {e}", file=sys.stderr)
        finally:
            self.stop()

    def send_buffer_loop(self):
        """Thread loop that periodically transmits buffered merged CAN data."""
        import time
        while self.running:
            # Sleep in small steps to react quickly to shutdown
            for _ in range(int(self.send_interval * 10)):
                if not self.running:
                    return
                time.sleep(0.1)
                
            # Grab and clear the buffer
            with self.buffer_lock:
                if not self.buffer:
                    continue
                merged_data = dict(self.buffer)
                self.buffer.clear()
            
            # Send the merged data to the node via UDS
            if self.forward_uds:
                print(f"[*] Sending merged CAN data ({len(merged_data)} frames) via UDS...")
                send_to_node(merged_data, self.uds_path)

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

def receive_can_frames(interface, forward_uds=False, uds_path="/tmp/p2p_node.sock", output_file=None, send_interval=10.0):
    """
    Runs candump receiver and blocks the main thread (blocking wrapper for CLI compatibility).
    """
    receiver = CandumpReceiver(interface, forward_uds=forward_uds, uds_path=uds_path, output_file=output_file, send_interval=send_interval)
    receiver.daemon = False  # Run blocking
    
    try:
        receiver.start()
        while receiver.is_alive():
            receiver.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\n[*] Stopping candump receiver...")
        receiver.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Receive CAN frames using candump and optionally forward them to P2P node.")
    parser.add_argument("interface", help="CAN interface to listen on (e.g., can0, vcan0)")
    parser.add_argument("-f", "--forward", action="store_true", help="Forward frames to P2P node via UDS")
    parser.add_argument("-o", "--output", help="File to write received CAN frames to (appends if exists)")
    parser.add_argument("--uds", default="/tmp/p2p_node.sock", help="Path to the UDS socket (default: /tmp/p2p_node.sock)")
    parser.add_argument("-i", "--interval", type=float, default=10.0, help="Interval in seconds to send merged CAN data (0 to send immediately)")
    
    args = parser.parse_args()
    
    uds_path = os.environ.get("UDS_PATH", args.uds)
    
    receive_can_frames(args.interface, forward_uds=args.forward, uds_path=uds_path, output_file=args.output, send_interval=args.interval)
