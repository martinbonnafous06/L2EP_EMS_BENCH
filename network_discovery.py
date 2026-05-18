import subprocess
import json
import socket
import os

def get_local_subnet():
    """Detects the local subnet (e.g., 192.168.1.0/24)."""
    # Simple heuristic for Linux
    try:
        # Get IP and mask from 'ip' command
        cmd = "ip -o -f inet addr show $(ip route get 8.8.8.8 | awk '{print $5}') | awk '{print $4}'"
        output = subprocess.check_output(cmd, shell=True).decode().strip()
        # Output is like 192.168.1.15/24, we want the network part
        ip_parts = output.split('/')
        base_ip = '.'.join(ip_parts[0].split('.')[:-1]) + '.0'
        return f"{base_ip}/{ip_parts[1]}"
    except Exception:
        return "192.168.1.0/24" # Fallback

def scan_for_peers(port=5555):
    """Uses nmap to find hosts with the specified port open."""
    subnet = get_local_subnet()
    print(f"[*] Scanning subnet {subnet} for port {port}...")
    
    try:
        # -p: port, --open: only show open ports, -n: no DNS resolution, -oG: grepable output
        cmd = ["nmap", "-p", str(port), "--open", "-n", "-oG", "-", subnet]
        output = subprocess.check_output(cmd).decode()
        
        peers = []
        for line in output.splitlines():
            if "Host:" in line and "Ports:" in line:
                ip = line.split()[1]
                # In this system, we don't know the node_id yet, so we use a placeholder or the IP
                # The node will identify itself via HELLO later anyway.
                peers.append(f"node_{ip.replace('.', '_')}:{ip}:{port}")
        
        return peers
    except FileNotFoundError:
        print("[!] Error: 'nmap' not found. Please install it: sudo apt install nmap")
        return []

if __name__ == "__main__":
    discovered_peers = scan_for_peers()
    with open("peers.json", "w") as f:
        json.dump(discovered_peers, f, indent=4)
    print(f"[*] Discovery complete. Found {len(discovered_peers)} peers. Saved to peers.json")
