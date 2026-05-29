import json
import os
import sys

def orchestrate():
    peers_file = "peers.json"
    if not os.path.exists(peers_file):
        print(f"[!] Error: {peers_file} not found. Run network_discovery.py first.")
        return

    try:
        with open(peers_file, "r") as f:
            peers = json.load(f)
    except Exception as e:
        print(f"[!] Error reading {peers_file}: {e}")
        return

    if not peers:
        print("[!] No peers found in peers.json.")
        return

    # Extract IPs
    ips = []
    for p in peers:
        try:
            _, ip, _ = p.split(':')
            ips.append(ip)
        except ValueError:
            continue

    if not ips:
        print("[!] Could not extract any IP addresses from peers.json.")
        return

    # Logic: Pick the first IP as the master, others as clients
    master_ip = ips[0]
    clients = ips[1:]

    print("=== Chrony Time Synchronization Plan ===")
    print(f"Master Node (Server): {master_ip}")
    print(f"Client Nodes: {', '.join(clients) if clients else 'None'}")
    print("-" * 40)
    
    print("\n1. RUN ON MASTER NODE:")
    print(f"   sudo bash setup_time.sh server")
    
    if clients:
        print("\n2. RUN ON ALL CLIENT NODES:")
        print(f"   sudo bash setup_time.sh client {master_ip}")
    
    print("\n" + "-" * 40)
    print("[*] After running, you can verify sync with: chronyc sources -v")

if __name__ == "__main__":
    orchestrate()
