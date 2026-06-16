import time
import os
import sys

# Add parent directory to path to allow importing from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.p2p_node import start_p2p_node

def main():
    # Configuration via environment or defaults
    port = int(os.environ.get("P2P_PORT", 5555))
    uds_path = os.environ.get("UDS_PATH", "/tmp/p2p_node.sock")
    
    # Start the node
    node = start_p2p_node(port=port, uds_path=uds_path)
    
    print("\n" + "="*40)
    print(" P2P COMMUNICATION NODE ACTIVE")
    print("="*40)
    print(f"Node ID:    {node.node_id}")
    print(f"IP Address: {node._get_local_ip()}")
    print(f"P2P Port:   {node.port}")
    print(f"UDS Socket: {node.uds_path}")
    print("="*40)
    print("\n[*] Waiting for messages (UDS) and peers (P2P)...")
    print("[*] Press Ctrl+C to stop.\n")

    try:
        last_peer_count = -1
        while True:
            time.sleep(2)
            
            # Only print when peer count changes to keep output clean
            peers = node.get_peers()
            if len(peers) != last_peer_count:
                print(f"[*] Network Status: {len(peers)} peer(s) online")
                if peers:
                    print(f"    - {', '.join(peers)}")
                last_peer_count = len(peers)
            
    except KeyboardInterrupt:
        node.shutdown()
        print("\n[*] Node stopped gracefully.")

if __name__ == "__main__":
    main()
