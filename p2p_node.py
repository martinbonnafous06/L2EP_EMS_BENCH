import zmq
import threading
import time
import sys
import json
import socket
import struct

class P2PNode:
    def __init__(self, node_id, port, known_peers_list=None):
        self.node_id = node_id
        self.port = int(port)
        self.context = zmq.Context()
        
        # Registry of active peers: { 'ID': {'ip': '...', 'port': ...} }
        self.peers = {}
        self.peers_lock = threading.Lock()
        
        # 1. Receiver (ROUTER) - Listen for everything
        self.receiver = self.context.socket(zmq.ROUTER)
        self.receiver.setsockopt_string(zmq.IDENTITY, self.node_id)
        self.receiver.bind(f"tcp://*:{self.port}")
        
        # 2. Senders (DEALERs) - One per peer
        self.senders = {}
        
        # Pre-populate if known
        if known_peers_list:
            for p_str in known_peers_list:
                p_id, p_ip, p_port = p_str.split(':')
                self._add_peer(p_id, p_ip, int(p_port))

    def _get_synced_time(self):
        """Returns local time. In a real lab, use 'chrony' or 'ntp' on the OS.
        Here we provide a placeholder for a synchronized timestamp."""
        return time.time()

    def _add_peer(self, peer_id, ip, port):
        with self.peers_lock:
            if peer_id not in self.peers:
                print(f"[*] New peer detected: {peer_id} @ {ip}:{port}")
                self.peers[peer_id] = {'ip': ip, 'port': port}
                
                # Create dedicated dealer for this peer
                sender = self.context.socket(zmq.DEALER)
                sender.setsockopt_string(zmq.IDENTITY, self.node_id)
                sender.connect(f"tcp://{ip}:{port}")
                self.senders[peer_id] = sender
                return True
        return False

    def listen_loop(self):
        """Background thread: Receives and processes all incoming messages."""
        print(f"[{self.node_id}] Listening on port {self.port}...")
        while True:
            try:
                # ROUTER receives [Identity, Payload]
                sender_id_bin, payload_bin = self.receiver.recv_multipart()
                sender_id = sender_id_bin.decode()
                data = json.loads(payload_bin.decode())
                
                # Handle Discovery 'HELLO'
                if data.get('type') == 'HELLO':
                    self._add_peer(sender_id, data['ip'], data['port'])
                
                print(f"\n[{self.node_id}] RECV from {sender_id} (T={data['timestamp']:.3f}): {data['content']}")
                
            except Exception as e:
                print(f"Error in listen_loop: {e}")

    def send_msg(self, peer_id, content, msg_type='DATA'):
        """Asynchronous send to a specific peer."""
        if peer_id in self.senders:
            payload = {
                'type': msg_type,
                'sender': self.node_id,
                'timestamp': self._get_synced_time(),
                'content': content,
                'ip': self._get_local_ip(), # For discovery
                'port': self.port
            }
            self.senders[peer_id].send_string(json.dumps(payload))
        else:
            print(f"Peer {peer_id} not connected.")

    def broadcast(self, content, msg_type='DATA'):
        """Send to everyone in the registry."""
        with self.peers_lock:
            target_ids = list(self.peers.keys())
        for p_id in target_ids:
            self.send_msg(p_id, content, msg_type)

    def _get_local_ip(self):
        """Helper to get the RPi IP on the ethernet interface."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def discovery_announcement(self):
        """Send HELLO to all initial known peers to trigger reciprocal discovery."""
        print("[*] Announcing presence to initial peers...")
        self.broadcast("Discovery HELLO", msg_type='HELLO')

def main():
    if len(sys.argv) < 3:
        print("Usage: python p2p_node.py <NODE_ID> <PORT> [PEER_ID:IP:PORT ...]")
        return

    node_id = sys.argv[1]
    port = sys.argv[2]
    initial_peers = sys.argv[3:] if len(sys.argv) > 3 else []

    node = P2PNode(node_id, port, initial_peers)

    # 1. Start Receiver Thread
    receiver_thread = threading.Thread(target=node.listen_loop, daemon=True)
    receiver_thread.start()

    # 2. Announce to known peers
    time.sleep(1)
    node.discovery_announcement()

    print(f"\n--- {node_id} READY (P2P) ---")
    print("Commands: \n  'all:<msg>' \n  '<id>:<msg>' \n  'list' to see peers")

    try:
        while True:
            cmd = input(f"[{node_id}] > ")
            if cmd == 'list':
                print(f"Peers: {list(node.peers.keys())}")
            elif ":" in cmd:
                target, msg = cmd.split(":", 1)
                if target == "all":
                    node.broadcast(msg)
                else:
                    node.send_msg(target, msg)
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()
