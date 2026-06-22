import sys
import os

# Add parent directory of core to sys.path to allow importing core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.p2p_node import send_p2p_data

def main():
    print("=== P2P External Sender Example ===")
    
    # 1. Define the message payload.
    # It can be a simple string or a structured dictionary representing telemetry data.
    message = {
        "type": "TELEMETRY",
        "power": 1500,  # W
        "soc": 82.5,    # %
        "voltage": 48.2 # V
    }
    
    # 2. Call the function send_p2p_data
    # - If a local P2PNode is running with a Unix Domain Socket (UDS), it will forward the message through it.
    # - Otherwise (or on Windows where UDS is unsupported), it automatically falls back to direct TCP/ZMQ P2P send to all peers in peers.json.
    print(f"[*] Sending message: {message}")
    success = send_p2p_data(message, peers_file="peers.json")
    
    if success:
        print("[+] Message sent successfully!")
    else:
        print("[-] Failed to send message. (Ensure peers.json contains active peers or a local node is active)")

if __name__ == "__main__":
    main()
