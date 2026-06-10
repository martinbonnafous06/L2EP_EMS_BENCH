import zmq
import threading
import time
import json
import socket

class P2PNode:
    def __init__(self, node_id, port, known_peers_list=None, peers_file=None, uds_path="/tmp/p2p_node.sock", on_message=None, state_file=None, data_log_file=None):
        """
        Initializes the P2P Node.
        :param node_id: Unique string identifier for this node.
        :param port: Port to listen on (ROUTER).
        :param known_peers_list: List of strings in format "ID:IP:PORT".
        :param peers_file: Optional path to save discovered peers to.
        :param uds_path: Path for the Unix Domain Socket listener.
        :param on_message: Optional callback function(sender_id, content) for received DATA messages.
        :param state_file: Optional path to log the latest state of all nodes as a JSON dictionary.
        :param data_log_file: Optional path to log all received data chronologically as a JSON list.
        """
        self.node_id = node_id
        self.port = int(port)
        self.peers_file = peers_file
        self.uds_path = uds_path
        self.on_message = on_message
        self.state_file = state_file
        self.data_log_file = data_log_file
        self.data_lock = threading.Lock()
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
        
        # Try to bind to the requested port, or find the next available one
        max_tries = 100
        for i in range(max_tries):
            try:
                current_port = self.port + i
                self.receiver.bind(f"tcp://*:{current_port}")
                self.port = current_port
                break
            except zmq.ZMQError as e:
                if i == max_tries - 1:
                    raise e
                continue
        
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
            threading.Thread(target=self.time_sync_loop, daemon=True),
            threading.Thread(target=self.uds_listen_loop, daemon=True)
        ]
        for t in self.threads:
            t.start()
        
        # Initial announcement
        time.sleep(1)
        self.broadcast("Discovery HELLO", msg_type='HELLO')
        print(f"[*] P2PNode '{self.node_id}' started on port {self.port}")
        if self.uds_path and hasattr(socket, 'AF_UNIX'):
            print(f"[*] UDS Listener active at {self.uds_path}")

    def uds_listen_loop(self):
        """Listens for local data on a Unix Domain Socket to broadcast to peers."""
        if not self.uds_path or not hasattr(socket, 'AF_UNIX'):
            if self.uds_path and not hasattr(socket, 'AF_UNIX'):
                print(f"[*] UDS not supported on this platform. UDS listener disabled for '{self.node_id}'.")
            return

        import os
        if os.path.exists(self.uds_path):
            os.remove(self.uds_path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(self.uds_path)
            server.listen(5)
            server.settimeout(1.0)
            
            while self.running:
                try:
                    conn, _ = server.accept()
                    with conn:
                        data = conn.recv(4096)
                        if data:
                            try:
                                # Try to parse as JSON
                                msg_data = json.loads(data.decode())
                                
                                # Check if it's a targeting command: {"target": "ID", "content": "..."}
                                if isinstance(msg_data, dict) and "target" in msg_data:
                                    target = msg_data["target"]
                                    content = msg_data.get("content", "")
                                    
                                    if target == "all" or not target:
                                        print(f"[*] UDS RECV: Broadcasting message")
                                        self.broadcast(content)
                                    else:
                                        print(f"[*] UDS RECV: Targeting peer {target}")
                                        self.send_msg(target, content)
                                else:
                                    # Just standard JSON data, broadcast it
                                    print(f"[*] UDS RECV: Broadcasting JSON data")
                                    self.broadcast(msg_data)
                                    
                            except ValueError:
                                # Not JSON, broadcast as raw string
                                content = data.decode().strip()
                                print(f"[*] UDS RECV: Broadcasting raw string")
                                self.broadcast(content)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Error in UDS loop: {e}")
        finally:
            server.close()
            if os.path.exists(self.uds_path):
                os.remove(self.uds_path)

    def _get_synced_time(self):
        """Returns the current system time plus the calculated synchronization offset."""
        return time.time() + self.time_offset

    def _save_peers(self):
        if not self.peers_file:
            return
            
        try:
            import os
            # 1. Load existing peers from file
            existing_peers = {}
            if os.path.exists(self.peers_file):
                try:
                    with open(self.peers_file, "r") as f:
                        file_content = json.load(f)
                        if isinstance(file_content, list):
                            for p_str in file_content:
                                try:
                                    p_id, p_ip, p_port = p_str.split(':')
                                    existing_peers[p_id] = {'ip': p_ip, 'port': int(p_port)}
                                except ValueError:
                                    pass
                except Exception as e:
                    print(f"[!] Error reading existing peers from {self.peers_file}: {e}")

            # 2. Merge with current active peers
            with self.peers_lock:
                active_peers_copy = {pid: {'ip': info['ip'], 'port': info['port']} for pid, info in self.peers.items()}

            # Resolve any conflicts: if an active peer has the same IP & port as an existing peer with a different ID,
            # we should remove the old ID from existing_peers to avoid duplicate/stale entries.
            for active_id, active_info in active_peers_copy.items():
                stale_ids = [
                    eid for eid, einfo in existing_peers.items()
                    if einfo['ip'] == active_info['ip'] and einfo['port'] == active_info['port'] and eid != active_id
                ]
                for stale_id in stale_ids:
                    del existing_peers[stale_id]
                
                # Update or add the active peer
                existing_peers[active_id] = active_info

            # 3. Format back to list of strings
            peer_list = [f"{pid}:{info['ip']}:{info['port']}" for pid, info in existing_peers.items()]
            
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
                        self._log_received_data(sender_id, data)
                        if self.on_message:
                            self.on_message(sender_id, data['content'])
                    
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

    def _log_received_data(self, sender_id, data):
        """Helper to log received data to JSON state file and chronological log file."""
        import os
        if not self.state_file and not self.data_log_file:
            return

        with self.data_lock:
            # 1. Update latest state file (flat list of objects with no duplicates)
            if self.state_file:
                state_list = []
                if os.path.exists(self.state_file):
                    try:
                        with open(self.state_file, 'r') as f:
                            file_content = json.load(f)
                            if isinstance(file_content, list):
                                state_list = file_content
                    except Exception:
                        pass
                
                # Build the flat entry
                entry = {
                    'sender': sender_id,
                    'timestamp': data.get('timestamp'),
                    'ip': data.get('ip'),
                    'port': data.get('port')
                }
                
                # Merge content keys directly at root level if content is a dictionary
                content = data.get('content')
                if isinstance(content, dict):
                    entry.update(content)
                else:
                    entry['content'] = content
                
                # Check for existing entry with the same sender to suppress duplicates
                found_idx = -1
                for idx, existing in enumerate(state_list):
                    if isinstance(existing, dict) and existing.get('sender') == sender_id:
                        found_idx = idx
                        break
                
                if found_idx != -1:
                    state_list[found_idx] = entry
                else:
                    state_list.append(entry)
                
                try:
                    with open(self.state_file, 'w') as f:
                        json.dump(state_list, f, indent=4)
                except Exception as e:
                    print(f"[!] Error writing state file {self.state_file}: {e}")

            # 2. Update chronological log file (array)
            if self.data_log_file:
                log_data = []
                if os.path.exists(self.data_log_file):
                    try:
                        with open(self.data_log_file, 'r') as f:
                            log_data = json.load(f)
                    except Exception:
                        pass
                
                if not isinstance(log_data, list):
                    log_data = []

                log_data.append({
                    'sender': sender_id,
                    'content': data.get('content'),
                    'timestamp': data.get('timestamp'),
                    'ip': data.get('ip'),
                    'port': data.get('port')
                })

                try:
                    with open(self.data_log_file, 'w') as f:
                        json.dump(log_data, f, indent=4)
                except Exception as e:
                    print(f"[!] Error writing data log file {self.data_log_file}: {e}")

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

    def send_message(self, content, peer_id=None):
        """
        Public API to send a message.
        If peer_id is provided, sends to that specific peer.
        Otherwise, broadcasts to all known peers.
        """
        if peer_id:
            self.send_msg(peer_id, content)
        else:
            self.broadcast(content)

    def shutdown(self):
        """Graceful cleanup of ZMQ and UDS resources."""
        print(f"[{self.node_id}] Shutting down...")
        self.running = False
        
        # Cleanup UDS socket file
        import os
        if self.uds_path and os.path.exists(self.uds_path):
            try:
                os.remove(self.uds_path)
            except:
                pass

        with self.peers_lock:
            with self.send_lock:
                for p_id, socket in self.senders.items():
                    socket.close()
                self.senders.clear()
        self.receiver.close()
        self.context.term()

def start_p2p_node(node_id=None, port=5555, peers_file="peers.json", uds_path="/tmp/p2p_node.sock"):
    """
    Helper function to quickly initialize and start a P2PNode.
    Handles environment variables and peer loading.
    """
    import os
    import socket
    
    # 1. Configuration
    if not node_id:
        hostname = socket.gethostname()
        node_id = os.environ.get("NODE_ID", hostname)
    
    port = int(os.environ.get("P2P_PORT", port))
    uds_path = os.environ.get("UDS_PATH", uds_path)
    
    # 2. Load discovered peers
    known_peers = []
    if peers_file and os.path.exists(peers_file):
        try:
            with open(peers_file, "r") as f:
                known_peers = json.load(f)
            print(f"[*] Loaded {len(known_peers)} peers from {peers_file}")
        except Exception as e:
            print(f"[!] Error loading {peers_file}: {e}")

    # 3. Initialize and Start Node
    node = P2PNode(node_id, port, known_peers, peers_file=peers_file, uds_path=uds_path)
    node.start()
    return node
