#!/bin/bash

# setup_time.sh - Automates Chrony time sync for Raspberry Pi Lab
# Usage:
#   sudo bash setup_time.sh server
#   sudo bash setup_time.sh client <server_ip>

ROLE=$1
SERVER_IP=$2

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo bash setup_time.sh ...)"
   exit 1
fi

echo "[*] Installing chrony..."
apt update && apt install chrony -y

# Backup original config
if [ ! -f /etc/chrony/chrony.conf.bak ]; then
    cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak
fi

if [ "$ROLE" == "server" ]; then
    echo "[*] Configuring as Chrony SERVER..."
    cat > /etc/chrony/chrony.conf <<EOF
# Use public NTP servers if internet is available
pool pool.ntp.org iburst

# Allow any node on the local subnet to sync (adjust if your subnet is different)
allow 192.168.137.0/24
allow 192.168.1.0/24

# Serve time even if internet is lost (Strata 10 makes this the master)
local stratum 10

# High precision logging
logtracking
logdir /var/log/chrony
EOF

elif [ "$ROLE" == "client" ]; then
    if [ -z "$SERVER_IP" ]; then
        echo "[!] Error: Client role requires a server IP address."
        echo "Example: sudo bash setup_time.sh client 192.168.137.101"
        exit 1
    fi
    echo "[*] Configuring as Chrony CLIENT, syncing to $SERVER_IP..."
    cat > /etc/chrony/chrony.conf <<EOF
# Sync to our local master server
server $SERVER_IP iburst

# Log adjustments
logtracking
logdir /var/log/chrony
EOF
else
    echo "Usage: sudo bash setup_time.sh server OR sudo bash setup_time.sh client <server_ip>"
    exit 1
fi

echo "[*] Restarting and enabling chrony service..."
systemctl restart chrony
systemctl enable chrony

echo "[*] Setup complete!"
echo "[*] To check sync status, run: chronyc sources -v"
echo "[*] To see time drift details, run: chronyc tracking"
