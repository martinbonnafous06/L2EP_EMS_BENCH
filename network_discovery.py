import subprocess
import json
import socket
import os

def get_local_subnet():
    """Detects the local subnet for eth0 or end0 (Raspberry Pi defaults)."""
    import ipaddress
    
    for interface in ['eth0', 'end0']:
        try:
            # Get IP and mask from 'ip' command for specific interface
            cmd = f"ip -o -f inet addr show {interface} | awk '{{print $4}}'"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
            
            if output:
                # Take the first IP if multiple are assigned
                addr_with_mask = output.split('\n')[0]
                # Use ipaddress to get the network address properly
                network = ipaddress.ip_network(addr_with_mask, strict=False)
                return str(network)
        except Exception:
            continue
    
    return None

def scan_for_peers(port=5555):
    """Uses nmap to find hosts with the specified port open."""
    subnet = get_local_subnet()
    if not subnet:
        print("[!] Error: No eth0 or end0 interface found. Skipping scan.")
        return []
        
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
