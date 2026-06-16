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

def scan_for_peers(port_range="5555-5565"):
    """Uses nmap to find hosts with any port in the specified range open."""
    subnet = get_local_subnet()
    if not subnet:
        print("[!] Error: No eth0 or end0 interface found. Skipping scan.")
        return []
        
    print(f"[*] Scanning subnet {subnet} for ports {port_range}...")
    
    try:
        # -p: port range, --open: only show open ports, -n: no DNS resolution, -oG: grepable output
        cmd = ["nmap", "-p", port_range, "--open", "-n", "-oG", "-", subnet]
        output = subprocess.check_output(cmd).decode()
        
        peers = []
        for line in output.splitlines():
            if "Host:" in line and "Ports:" in line:
                ip = line.split()[1]
                # Extract the port(s) found open
                # Line format: Host: 192.168.1.10 () Ports: 5555/open/tcp//...
                ports_part = line.split("Ports: ")[1]
                for p_info in ports_part.split(", "):
                    if "/open/" in p_info:
                        found_port = p_info.split("/")[0]
                        peers.append(f"node_{ip.replace('.', '_')}_{found_port}:{ip}:{found_port}")
        
        return peers
    except FileNotFoundError:
        print("[!] Error: 'nmap' not found. Please install it: sudo apt install nmap")
        return []

if __name__ == "__main__":
    discovered_peers = scan_for_peers()
    with open("peers.json", "w") as f:
        json.dump(discovered_peers, f, indent=4)
    print(f"[*] Discovery complete. Found {len(discovered_peers)} peers. Saved to peers.json")
