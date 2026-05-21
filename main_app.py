import time
import json
import os
import sys
from p2p_node import P2PNode

def main():
    # 1. Configuration
    import socket
    hostname = socket.gethostname()
    node_id = os.environ.get("NODE_ID", f"{hostname}_{os.getpid()}")
    port = int(os.environ.get("P2P_PORT", 5555))
    
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
    node = P2PNode(node_id, port, known_peers, peers_file=peers_file)
    node.start()

    print(f"\n--- {node_id} RUNNING ---")
    print("Press Ctrl+C to stop.")

    try:
        # 4. Automated Task Loop (Simulated Experiment)
        counter = 0
        while True:
            time.sleep(10)
            counter += 1
            status_msg = f"Heartbeat check #{counter} - Load: {os.getloadavg() if hasattr(os, 'getloadavg') else 'N/A'}"
            node.broadcast(status_msg)
            
            # Show current peer count
            active_peers = node.get_peers()
            print(f"[*] Periodic broadcast sent. Active peers: {len(active_peers)} {active_peers}")
            
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()

if __name__ == "__main__":
    main()
