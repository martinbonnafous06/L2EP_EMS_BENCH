import zmq
import threading
import time
import json
import socket

class P2PNode:
    def __init__(self, node_id, port, known_peers_list=None):
        """
        Initializes the P2P Node.
        :param node_id: Unique string identifier for this node.
        :param port: Port to listen on (ROUTER).
        :param known_peers_list: List of strings in format "ID:IP:PORT".
        """
        self.node_id = node_id
        self.port = int(port)
        self.context = zmq.Context()
        self.running = True
        self.heartbeat_interval = 2 # seconds
        self.timeout_threshold = self.heartbeat_interval * 3
        
        # Registry of active peers: { 'ID': {'ip': '...', 'port': ..., 'last_seen': float} }
        self.peers = {}
        self.peers_lock = threading.Lock()
        
        # 1. Receiver (ROUTER) - Listen for everything
        self.receiver = self.context.socket(zmq.ROUTER)
        self.receiver.setsockopt_string(zmq.IDENTITY, self.node_id)
        self.receiver.setsockopt(zmq.LINGER, 0)
        self.receiver.bind(f"tcp://*:{self.port}")
        
        # 2. Senders (DEALERs) - One per peer
        self.senders = {}
        
        # Pre-populate if known
        if known_peers_list:
            for p_str in known_peers_list:
                try:
                    p_id, p_ip, p_port = p_str.split(':')
                    self._add_peer(p_id, p_ip, int(p_port))
                except ValueError:
                    print(f"Invalid peer format: {p_str}. Use ID:IP:PORT")

    def start(self):
        """Starts background threads for listening and heartbeats."""
        self.threads = [
            threading.Thread(target=self.listen_loop, daemon=True),
            threading.Thread(target=self.heartbeat_loop, daemon=True)
        ]
        for t in self.threads:
            t.start()
        
        # Initial announcement
        time.sleep(1)
        self.broadcast("Discovery HELLO", msg_type='HELLO')
        print(f"[*] P2PNode '{self.node_id}' started on port {self.port}")

    def _get_synced_time(self):
        """Returns local time. For lab accuracy, use NTP/Chrony on the OS."""
        return time.time()

    def _add_peer(self, peer_id, ip, port):
        with self.peers_lock:
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
                return True
            else:
                # Just update the last_seen if already exists
                self.peers[peer_id]['last_seen'] = time.time()
        return False

    def listen_loop(self):
        """Background thread: Receives and processes all incoming messages."""
        while self.running:
            try:
                if self.receiver.poll(timeout=1000):
                    sender_id_bin, payload_bin = self.receiver.recv_multipart()
                    sender_id = sender_id_bin.decode()
                    data = json.loads(payload_bin.decode())
                    
                    with self.peers_lock:
                        if sender_id in self.peers:
                            self.peers[sender_id]['last_seen'] = time.time()
                        elif data.get('type') == 'HELLO':
                            self._add_peer(sender_id, data['ip'], data['port'])
                    
                    if data.get('type') == 'DATA':
                        # In a library, you'd likely use a callback here
                        print(f"[{self.node_id}] RECV from {sender_id}: {data['content']}")
                
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

    def _remove_peer(self, peer_id):
        with self.peers_lock:
            if peer_id in self.peers:
                del self.peers[peer_id]
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
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def shutdown(self):
        """Graceful cleanup of ZMQ resources."""
        print(f"[{self.node_id}] Shutting down...")
        self.running = False
        with self.peers_lock:
            for p_id, socket in self.senders.items():
                socket.close()
            self.senders.clear()
        self.receiver.close()
        self.context.term()
