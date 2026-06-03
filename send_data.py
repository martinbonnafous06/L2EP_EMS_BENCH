import socket
import sys
import json
import os
import argparse

def send_to_node(message, target=None, uds_path="/tmp/p2p_node.sock"):
    """Sends data to the local P2P node via Unix Domain Socket."""
    
    if not os.path.exists(uds_path):
        print(f"[!] Error: UDS socket not found at {uds_path}")
        print("    Ensure the P2P node is running (run_node.py).")
        return

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(uds_path)
            
            # Prepare payload for the P2P node
            # We use a specific structure to tell the node whether to target or broadcast
            payload_dict = {
                "target": target, # "all" or specific node_id
                "content": message
            }
            
            client.sendall(json.dumps(payload_dict).encode())
            
            if target and target != "all":
                print(f"[+] Message sent to {target}: {message}")
            else:
                print(f"[+] Message broadcasted to all: {message}")
            
    except ConnectionRefusedError:
        print(f"[!] Error: Connection refused. Is the node listening?")
    except Exception as e:
        print(f"[!] Error sending message: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send messages to the P2P network.")
    parser.add_argument("message", nargs="?", default="Hello from send_data.py", help="The message to send")
    parser.add_argument("-t", "--target", help="Specific Node ID to target (default: broadcast)")
    parser.add_argument("--uds", default="/tmp/p2p_node.sock", help="Path to the UDS socket")
    
    args = parser.parse_args()
    
    # Override UDS path if environment variable is set
    uds_path = os.environ.get("UDS_PATH", args.uds)
    
    send_to_node(args.message, target=args.target, uds_path=uds_path)
