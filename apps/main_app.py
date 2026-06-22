import time
import json
import os
import sys
import argparse

# Add parent directory to path to allow importing from core/can_bus
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.p2p_node import P2PNode
from core.influx_logger import InfluxDBLogger

def main():
    # 1. Configuration / Arguments
    import socket
    hostname = socket.gethostname()
    
    parser = argparse.ArgumentParser(description="P2P EMS Node Main Application")
    parser.add_argument("-n", "--node-id", default=os.environ.get("NODE_ID", hostname), help="Unique node identifier (default: hostname or env NODE_ID)")
    parser.add_argument("-p", "--port", type=int, default=int(os.environ.get("P2P_PORT", 5555)), help="P2P listening port (default: 5555 or env P2P_PORT)")
    parser.add_argument("-f", "--file", default="data-sent.json", help="JSON file containing telemetry to broadcast (default: data-sent.json)")
    parser.add_argument("-i", "--interval", type=float, default=10.0, help="Broadcast interval for the telemetry file in seconds (default: 10.0)")
    parser.add_argument("-c", "--can", help="Optional CAN interface to receive frames from (e.g. can0, vcan0)")
    parser.add_argument("--can-interval", type=float, default=10.0, help="Interval to send merged CAN data in seconds (default: 10.0)")
    parser.add_argument("--uds", default=os.environ.get("UDS_PATH", "/tmp/p2p_node.sock"), help="Path to UDS socket (default: /tmp/p2p_node.sock)")
    
    args = parser.parse_args()
    
    node_id = args.node_id
    port = args.port
    uds_path = args.uds
    
    # Check if we should log history (automatic for dSpace orchestrator, or if requested via env)
    save_history = os.environ.get("SAVE_HISTORY", "false").lower() in ("true", "1", "yes")
    if node_id == "Pi5_dSpace":
        save_history = True
    
    data_log_file = "data-recieved-history.json" if save_history else None
    if save_history:
        print(f"[*] History logging enabled. Saving chronological log to {data_log_file}")
    
    # 2. Load discovered peers
    peers_file = "peers.json"
    known_peers = []
    if os.path.exists(peers_file):
        try:
            with open(peers_file, "r") as f:
                known_peers = json.load(f)
            print(f"[*] Loaded {len(known_peers)} peers from {peers_file}")
        except Exception as e:
            print(f"[!] Error loading peers.json: {e}")

    # 3. Initialize InfluxDB logger and P2P Node (starts router receiver, heartbeat, time sync, and UDS loops)
    influx_logger = InfluxDBLogger()
    
    def on_message_received(sender_id, content):
        influx_logger.log_message(sender_id, content)
        
    node = P2PNode(
        node_id=node_id,
        port=port,
        known_peers_list=known_peers, 
        peers_file=peers_file, 
        uds_path=uds_path,
        on_message=on_message_received,
        state_file="data-recieved.json", 
        data_log_file=data_log_file
    )
    node.start()

    # 4. Initialize and Start CAN receiver thread if interface specified
    can_receiver = None
    if args.can:
        try:
            from can_bus.candump_receiver import CandumpReceiver
            can_receiver = CandumpReceiver(
                interface=args.can,
                forward_uds=True,
                uds_path=uds_path,
                send_interval=args.can_interval
            )
            can_receiver.start()
        except ImportError as e:
            print(f"[!] Error importing CandumpReceiver: {e}. Ensure can_bus/candump_receiver.py exists.", file=sys.stderr)

    print(f"\n--- {node_id} RUNNING ---")
    if args.can:
        print(f"[*] Capturing CAN frames from '{args.can}' and broadcasting merged state every {args.can_interval}s")
    print(f"[*] Broadcasting telemetry from file '{args.file}' every {args.interval}s")
    print("Press Ctrl+C to stop.")

    try:
        # 5. Automated Telemetry File Broadcast Loop
        while True:
            # Read and broadcast data from the custom file
            data_to_send = {}
            if os.path.exists(args.file):
                try:
                    with open(args.file, "r") as f:
                        data_to_send = json.load(f)
                    node.broadcast(data_to_send)
                    print(f"[*] Broadcasted data from '{args.file}': {data_to_send}")
                    # Log our own telemetry to InfluxDB
                    influx_logger.log_message(node_id, data_to_send)
                except Exception as e:
                    print(f"[!] Error reading/broadcasting '{args.file}': {e}")
            else:
                print(f"[!] File '{args.file}' not found. Skipping this broadcast cycle.")
            
            # Show current peer count and synced time status
            active_peers = node.get_peers()
            synced_time = node._get_synced_time()
            time_str = time.strftime('%H:%M:%S', time.localtime(synced_time))
            print(f"[*] Time: {time_str} (Offset: {node.time_offset:+.6f}s) | Active peers: {len(active_peers)}")
            
            # Wait for next cycle
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n[*] Stopping main application...")
    finally:
        if can_receiver:
            can_receiver.stop()
        node.shutdown()
        influx_logger.shutdown()

if __name__ == "__main__":
    main()
