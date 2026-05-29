import zmq
import threading
import time
import json
import socket

class P2PNode:
    def __init__(self, node_id, port, known_peers_list=None, peers_file=None):
        """
        Initializes the P2P Node.
        :param node_id: Unique string identifier for this node.
        :param port: Port to listen on (ROUTER).
        :param known_peers_list: List of strings in format "ID:IP:PORT".
        :param peers_file: Optional path to save discovered peers to.
        """
        self.node_id = node_id
        self.port = int(port)
        self.peers_file = peers_file
        self.context = zmq.Context()
        self.running = True
        self.heartbeat_interval = 2 # seconds
        self.timeout_threshold = 10 
        
        # Registry of active peers: { 'ID': {'ip': '...', 'port': ..., 'last_seen': float} }
        self.peers = {}
        self.peers_lock = threading.Lock()
        
        # Time Synchronization
        self.time_offset = 0.0
        self.sync_interval = 10.0 # seconds
        self.offsets = {} # {peer_id: last_offset}
        
        # 1. Receiver (ROUTER) - Listen for everything
        self.receiver = self.context.socket(zmq.ROUTER)
        self.receiver.setsockopt_string(zmq.IDENTITY, self.node_id)
        self.receiver.setsockopt(zmq.LINGER, 0)
        self.receiver.bind(f"tcp://*:{self.port}")
        
        # 2. Senders (DEALERs) - One per peer
        self.senders = {}
        # ZMQ sockets are not thread-safe, so we need a lock for sending
        self.send_lock = threading.Lock()
        
        # Pre-populate if known
        if known_peers_list:
            for p_str in known_peers_list:
                try:
                    p_id, p_ip, p_port = p_str.split(':')
                    self._add_peer(p_id, p_ip, int(p_port), save=False)
                except ValueError:
                    print(f"Invalid peer format: {p_str}. Use ID:IP:PORT")

    def start(self):
        """Starts background threads for listening and heartbeats."""
        self.threads = [
            threading.Thread(target=self.listen_loop, daemon=True),
            threading.Thread(target=self.heartbeat_loop, daemon=True),
            threading.Thread(target=self.time_sync_loop, daemon=True)
        ]
        for t in self.threads:
            t.start()
        
        # Initial announcement
        time.sleep(1)
        self.broadcast("Discovery HELLO", msg_type='HELLO')
        print(f"[*] P2PNode '{self.node_id}' started on port {self.port}")

    def _get_synced_time(self):
        """Returns the current system time plus the calculated synchronization offset."""
        return time.time() + self.time_offset

    def _save_peers(self):
        if not self.peers_file:
            return
            
        try:
            with self.peers_lock:
                peer_list = [f"{pid}:{info['ip']}:{info['port']}" for pid, info in self.peers.items()]
            
            with open(self.peers_file, "w") as f:
                json.dump(peer_list, f, indent=4)
        except Exception as e:
            print(f"[!] Error saving to {self.peers_file}: {e}")

    def _add_peer(self, peer_id, ip, port, save=True):
        if not ip or not port or peer_id == self.node_id:
            return False

        with self.peers_lock:
            # 1. Check if we already have this IP/Port under a different ID
            existing_id = None
            for p_id, info in self.peers.items():
                if info['ip'] == ip and info['port'] == port:
                    existing_id = p_id
                    break
            
            if existing_id and existing_id != peer_id:
                print(f"[*] Reconciling identity: {existing_id} -> {peer_id}")
                with self.send_lock: # Ensure we don't close while sending
                    if existing_id in self.senders:
                        self.senders[existing_id].close()
                        del self.senders[existing_id]
                del self.peers[existing_id]

            # 2. Add or Update the peer
            if peer_id not in self.peers:
                print(f"[*] New peer detected: {peer_id} @ {ip}:{port}")
                
                # Create dedicated dealer for this peer
                sender = self.context.socket(zmq.DEALER)
                sender.setsockopt_string(zmq.IDENTITY, self.node_id)
                sender.setsockopt(zmq.LINGER, 0)
                sender.connect(f"tcp://{ip}:{port}")
                
                self.senders[peer_id] = sender
                self.peers[peer_id] = {
                    'ip': ip, 
                    'port': port, 
                    'last_seen': time.time()
                }
                new_peer_added = True
            else:
                self.peers[peer_id]['last_seen'] = time.time()
                new_peer_added = False
        
        if (new_peer_added or existing_id) and save:
            self._save_peers()
            
        return new_peer_added

    def listen_loop(self):
        """Background thread: Receives and processes all incoming messages."""
        while self.running:
            try:
                if self.receiver.poll(timeout=1000):
                    sender_id_bin, payload_bin = self.receiver.recv_multipart()
                    sender_id = sender_id_bin.decode()
                    data = json.loads(payload_bin.decode())
                    
                    self._add_peer(sender_id, data.get('ip'), data.get('port'))
                    
                    msg_type = data.get('type')
                    if msg_type == 'DATA':
                        print(f"[{self.node_id}] RECV from {sender_id}: {data['content']}")
                    
                    elif msg_type == 'TIME_REQ':
                        # Respond with our current synced time
                        self.send_msg(sender_id, {"t_orig": data['content']['t_orig']}, msg_type='TIME_RES')
                    
                    elif msg_type == 'TIME_RES':
                        # Only sync to the "Time Master" (lowest node_id among active peers + self)
                        active_peers = self.get_peers()
                        all_nodes = sorted(active_peers + [self.node_id])
                        master_id = all_nodes[0]
                        
                        if sender_id == master_id:
                            t_4 = time.time()
                            t_orig = data['content']['t_orig']
                            t_server = data['timestamp'] # Peer's synced time
                            rtt = t_4 - t_orig
                            
                            # Christian's algorithm: T_new = T_server + RTT/2
                            offset_sample = (t_server + rtt/2) - t_4
                            
                            # Use a moving average for smoothness
                            self.time_offset = 0.8 * self.time_offset + 0.2 * offset_sample
                            # print(f"[*] Synced with Master {master_id}: Offset {self.time_offset:+.6f}s")
                
            except zmq.ZMQError:
                if not self.running: break
            except Exception as e:
                print(f"Error in listen_loop: {e}")

    def heartbeat_loop(self):
        """Background thread: Sends PINGs and cleans up dead nodes."""
        while self.running:
            try:
                self.broadcast("PING", msg_type='PING')
                
                now = time.time()
                dead_peers = []
                with self.peers_lock:
                    for p_id, info in self.peers.items():
                        if now - info['last_seen'] > self.timeout_threshold:
                            dead_peers.append(p_id)
                
                for p_id in dead_peers:
                    print(f"[*] Peer {p_id} timed out. Removing.")
                    self._remove_peer(p_id)
                    
            except Exception as e:
                print(f"Error in heartbeat_loop: {e}")
            
            time.sleep(self.heartbeat_interval)

    def time_sync_loop(self):
        """Background thread: Periodically requests time from all peers."""
        while self.running:
            try:
                # Send TIME_REQ with local (unsynced) timestamp
                self.broadcast({"t_orig": time.time()}, msg_type='TIME_REQ')
            except Exception as e:
                print(f"Error in time_sync_loop: {e}")
            
            time.sleep(self.sync_interval)

    def _remove_peer(self, peer_id):
        with self.peers_lock:
            if peer_id in self.peers:
                del self.peers[peer_id]
            if peer_id in self.offsets:
                del self.offsets[peer_id]
            with self.send_lock:
                if peer_id in self.senders:
                    self.senders[peer_id].close()
                    del self.senders[peer_id]

    def send_msg(self, peer_id, content, msg_type='DATA'):
        """Asynchronous send to a specific peer."""
        with self.peers_lock:
            sender_socket = self.senders.get(peer_id)
            
        if sender_socket:
            try:
                payload = {
                    'type': msg_type,
                    'sender': self.node_id,
                    'timestamp': self._get_synced_time(),
                    'content': content,
                    'ip': self._get_local_ip(),
                    'port': self.port
                }
                # ZMQ sockets are not thread-safe, use global send lock
                with self.send_lock:
                    sender_socket.send_string(json.dumps(payload))
            except zmq.ZMQError as e:
                print(f"Failed to send to {peer_id}: {e}")

    def broadcast(self, content, msg_type='DATA'):
        """Send to everyone in the registry."""
        with self.peers_lock:
            target_ids = list(self.peers.keys())
        for p_id in target_ids:
            self.send_msg(p_id, content, msg_type)

    def get_peers(self):
        """Returns the list of currently active peer IDs."""
        with self.peers_lock:
            return list(self.peers.keys())

    def _get_local_ip(self):
        """Specifically look for eth0 or end0 interfaces, avoiding Docker IPs."""
        import subprocess
        for interface in ['eth0', 'end0']:
            try:
                cmd = f"ip -o -f inet addr show {interface} | awk '{{print $4}}' | cut -d/ -f1"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
                if output:
                    return output.split('\n')[0]
            except Exception:
                continue

        try:
            cmd = "ip -o -f inet addr show | grep -v 'lo' | awk '{print $4}' | cut -d/ -f1"
            all_ips = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip().split('\n')
            for ip in all_ips:
                if not ip: continue
                if ip.startswith('172.'):
                    parts = ip.split('.')
                    if 16 <= int(parts[1]) <= 31:
                        continue
                if ip.startswith('192.168.48.') or ip.startswith('192.168.49.'):
                    continue
                return ip
        except Exception:
            pass

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except Exception:
            return '127.0.0.1'
        finally:
            s.close()

    def shutdown(self):
        """Graceful cleanup of ZMQ resources."""
        print(f"[{self.node_id}] Shutting down...")
        self.running = False
        with self.peers_lock:
            with self.send_lock:
                for p_id, socket in self.senders.items():
                    socket.close()
                self.senders.clear()
        self.receiver.close()
        self.context.term()
