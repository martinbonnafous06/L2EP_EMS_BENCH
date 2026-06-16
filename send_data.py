import os
import argparse
from p2p_node import send_to_node

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send messages to the P2P network.")
    parser.add_argument("message", nargs="?", default="Hello from send_data.py", help="The message to send")
    parser.add_argument("-t", "--target", help="Specific Node ID to target (default: broadcast)")
    parser.add_argument("--uds", default="/tmp/p2p_node.sock", help="Path to the UDS socket")
    
    args = parser.parse_args()
    
    # Override UDS path if environment variable is set
    uds_path = os.environ.get("UDS_PATH", args.uds)
    
    send_to_node(args.message, target=args.target, uds_path=uds_path)
