import time
import json
import os
import sys
# Add parent directory to path to allow importing from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.p2p_node import P2PNode

def main():
    # 1. Configuration
    import socket
    hostname = socket.gethostname()
    node_id = os.environ.get("NODE_ID", hostname)
    port = int(os.environ.get("P2P_PORT", 5555))
    
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

    # 3. Initialize and Start Node
    node = P2PNode(node_id, port, known_peers, peers_file=peers_file, state_file="data-recieved.json", data_log_file=data_log_file)
    node.start()

    print(f"\n--- {node_id} RUNNING ---")
    print("Press Ctrl+C to stop.")

    try:
        # 4. Automated Task Loop (Simulated Experiment)
        while True:
            time.sleep(10)
            
            # Read data from data-sent.json
            data_to_send = {}
            if os.path.exists("data-sent.json"):
                try:
                    with open("data-sent.json", "r") as f:
                        data_to_send = json.load(f)
                except Exception as e:
                    print(f"[!] Error reading data-sent.json: {e}")
            else:
                print(f"[!] data-sent.json not found, sending empty object.")
            
            node.broadcast(data_to_send)
            print(f"[*] Broadcasted data from data-sent.json: {data_to_send}")
            
            # Show current peer count and synced time
            active_peers = node.get_peers()
            synced_time = node._get_synced_time()
            time_str = time.strftime('%H:%M:%S', time.localtime(synced_time))
            print(f"[*] Time: {time_str} (Offset: {node.time_offset:+.6f}s) | Active peers: {len(active_peers)}")
            
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()

if __name__ == "__main__":
    main()
