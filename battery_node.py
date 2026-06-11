import time
import json
import os
import argparse
from datetime import datetime
try:
    from .p2p_node import P2PNode
except (ImportError, ValueError):
    from p2p_node import P2PNode

LOG_FILE = "battery-can.log"

def handle_message(sender_id, content):
    """Callback for when the P2P node receives a DATA message."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_line = f"[{timestamp}] RECV from {sender_id}: {content}\n"
        
        # Write the received data onto the file named battery-can
        with open(LOG_FILE, 'a') as f:
            f.write(log_line)
            
        # Also print to console for visibility
        print(log_line.strip())
    except Exception as e:
        print(f"Error handling message: {e}")

def main():
    parser = argparse.ArgumentParser(description="Battery CAN simulator over P2P")
    parser.add_argument("--node-id", default=f"battery-{os.getpid()}", help="Unique ID for this node")
    parser.add_argument("-p", "--port", type=int, default=5556, help="Port to listen on")
    parser.add_argument("--state-file", default="latest_states.json", help="Path to JSON file storing the latest state of all nodes")
    parser.add_argument("--log-file", default="received_data_log.json", help="Path to JSON file storing chronological log of all data")
    args = parser.parse_args()

    print(f"[*] Starting Battery Node: {args.node_id}")

    # Load peers if available
    peers_file = "peers.json"
    known_peers = []
    if os.path.exists(peers_file):
        try:
            with open(peers_file, "r") as f:
                known_peers = json.load(f)
        except Exception:
            pass

    # Initialize the P2P Node with our custom on_message callback
    node = P2PNode(
        node_id=args.node_id,
        port=args.port,
        known_peers_list=known_peers,
        peers_file=peers_file,
        uds_path=f"/tmp/{args.node_id}.sock",
        on_message=handle_message,
        state_file=args.state_file,
        data_log_file=args.log_file
    )
    node.start()

    print(f"[*] Logging received data to '{LOG_FILE}'")
    print("[*] Simulating and broadcasting Battery CAN data. Press Ctrl+C to stop.")

    try:
        counter = 0
        while True:
            # Simulate generating some battery CAN data
            # e.g., ID: 0x1A2, Data containing Voltage and SOC
            voltage = 400.0 + (counter % 10) * 0.5
            soc = 80 - (counter % 5)
            
            simulated_can_frame = {
                "type": "CAN_FRAME",
                "id": "1A2",
                "interface": "virtual",
                "data": f"V:{voltage:.1f} SOC:{soc}%",
                "timestamp": time.time()
            }
            
            # Broadcast the simulated CAN frame over the P2P network
            node.broadcast(simulated_can_frame)
            print(f"[*] SENT over P2P: {simulated_can_frame['data']}")
            
            counter += 1
            time.sleep(10) # Send data every 10 seconds

    except KeyboardInterrupt:
        print("\n[*] Stopping battery node...")
    finally:
        node.shutdown()

if __name__ == "__main__":
    main()
