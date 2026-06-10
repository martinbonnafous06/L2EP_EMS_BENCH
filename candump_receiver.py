import subprocess
import re
import argparse
import sys
import json
import socket
import os

def send_to_node(message, uds_path="/tmp/p2p_node.sock"):
    """Sends parsed CAN data to the local P2P node via Unix Domain Socket."""
    if not os.path.exists(uds_path):
        return False
    try:
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

def receive_can_frames(interface, forward_uds=False, uds_path="/tmp/p2p_node.sock", output_file=None):
    """
    Runs candump as a subprocess and parses its output line by line.
    Uses the -L option to output in log format: (timestamp) interface ID#DATA
    """
    print(f"[*] Starting candump on interface '{interface}'...")
    try:
        # -L outputs log format: (1612345678.123456) can0 123#1122334455667788
        process = subprocess.Popen(
            ['candump', '-L', interface],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        print("[!] Error: 'candump' command not found. Is can-utils installed?")
        print("    Try running: sudo apt-get install can-utils")
        sys.exit(1)

    # Regex to parse the candump -L format
    # Example: (1612345678.123456) vcan0 123#11223344
    log_pattern = re.compile(r"\((\d+\.\d+)\)\s+(\S+)\s+([\da-fA-F]+)#([\da-fA-F]*)")

    file_handle = None
    if output_file:
        try:
            file_handle = open(output_file, 'a')
            print(f"[*] Logging frames to file: {output_file}")
        except IOError as e:
            print(f"[!] Error opening output file: {e}")
            sys.exit(1)

    try:
        for line in process.stdout:
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
                
                # Write to file if an output file was specified
                if file_handle:
                    file_handle.write(log_msg + "\n")
                    file_handle.flush() # Ensure it's written immediately
                
                if forward_uds:
                    send_to_node(frame, uds_path)
            else:
                print(f"[?] Unrecognized format: {line}")
                
    except KeyboardInterrupt:
        print("\n[*] Stopping candump receiver...")
    finally:
        if file_handle:
            file_handle.close()
        process.terminate()
        process.wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Receive CAN frames using candump and optionally forward them to P2P node.")
    parser.add_argument("interface", help="CAN interface to listen on (e.g., can0, vcan0)")
    parser.add_argument("-f", "--forward", action="store_true", help="Forward frames to P2P node via UDS")
    parser.add_argument("-o", "--output", help="File to write received CAN frames to (appends if exists)")
    parser.add_argument("--uds", default="/tmp/p2p_node.sock", help="Path to the UDS socket (default: /tmp/p2p_node.sock)")
    
    args = parser.parse_args()
    
    uds_path = os.environ.get("UDS_PATH", args.uds)
    
    receive_can_frames(args.interface, forward_uds=args.forward, uds_path=uds_path, output_file=args.output)
