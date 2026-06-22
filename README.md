# 🚀 L2EP EMS Bench - P2P & CAN Control System

This repository contains the software layer for the **Distributed Battery Control Testbench** developed at the **Laboratoire d’Électrotechnique et d’Électronique de Puissance (L2EP)** in collaboration with **Centrale Lille IG2I**. 

The system enables real-time Peer-to-Peer (P2P) communication and Hardware-in-the-Loop (HIL) orchestration between Raspberry Pi nodes controlling battery units and a dSpace simulator.

---

## 📌 Architecture Overview

Each Raspberry Pi acts as a standalone peer executing a Python process that establishes:
*   A ZeroMQ P2P network using `zmq.ROUTER` / `zmq.DEALER` topology (brokerless).
*   A local communication bridge (Unix Domain Sockets on Linux, direct ZMQ TCP on Windows) to receive and broadcast telemetry and CAN messages.
*   Automatic clock synchronization using **Christian's Algorithm** (with master election) to align battery telemetry timestamps.

---

## 🛠 Using `main_app.py`

[`apps/main_app.py`](file:///C:/Users/marti/Desktop/STAGE/DEV/apps/main_app.py) is the primary application entry point. It manages local hardware interfaces (CAN bus via `candump`), loads local telemetry files, logs incoming states, and participates in the P2P network.

### CLI Arguments

| Argument | Long Option | Default | Description |
| :--- | :--- | :--- | :--- |
| `-n` | `--node-id` | `hostname` / `$NODE_ID` | Unique identifier for the node on the network. |
| `-p` | `--port` | `5555` / `$P2P_PORT` | ZeroMQ port to listen on. Fallbacks to `5555+i` if busy. |
| `-f` | `--file` | `data-sent.json` | Path to the local JSON telemetry file to broadcast. |
| `-i` | `--interval` | `10.0` | Telemetry broadcast interval in seconds. |
| `-c` | `--can` | `None` | CAN interface to capture frames from (e.g. `can0`, `vcan0`). |
| `--can-interval` | | `10.0` | Buffer/merge interval for CAN frames before broadcasting. |
| `--uds` | | `/tmp/p2p_node.sock` | Path to the Unix Domain Socket (UDS) control bridge. |

### Run Command Examples

*   **Simple P2P Node (No CAN, reads telemetry file):**
    ```bash
    python apps/main_app.py --node-id Pi5_Alpha --port 5555 --file data-sent.json --interval 10
    ```

*   **Orchestration / Battery Node (With CAN Bus listener):**
    Capture raw frames from interface `can0`, buffer them for `5` seconds, convert them to JSON, and broadcast them:
    ```bash
    python apps/main_app.py --node-id Pi5_Beta --can can0 --can-interval 5.0
    ```

---

## 📊 Data Structures & JSON Schemas

### 1. Telemetry Broadcast Data (`data-sent.json`)
The application periodically reads a local file containing the battery status and broadcasts it as a JSON payload.
```json
{
    "power": 1500.0,
    "soc": 75.0,
    "voltage": 48.0
}
```

### 2. P2P Network Envelope
Every message sent across the ZeroMQ network is wrapped in a structured P2P envelope:
```json
{
    "type": "DATA",
    "sender": "Pi5_Alpha",
    "timestamp": 1781081907.1107757,
    "content": <PAYLOAD>,
    "ip": "192.168.1.10",
    "port": 5555
}
```

---

## 🔌 CAN Bus to JSON conversion & Broadcast

When `--can` is specified, the application launches a background thread running the [`CandumpReceiver`](file:///C:/Users/marti/Desktop/STAGE/DEV/can_bus/candump_receiver.py).

### How it works:
1. **Raw Capture:** The script spawns a sub-process running `candump -L <interface>` (part of standard Linux `can-utils`).
2. **Regex Parsing:** It captures the standard SocketCAN log line format:
   ```text
   (1612345678.123456) can0 1A2#0102030405060708
   ```
3. **JSON Conversion:** The raw line is parsed into a structured JSON frame:
   ```json
   {
       "timestamp": 1612345678.123456,
       "interface": "can0",
       "id": "1A2",
       "data": "0102030405060708",
       "type": "CAN_FRAME"
   }
   ```
4. **Buffering & Merging:**
   * **If `--can-interval > 0` (Default: 10s):** Frames are collected into an in-memory list buffer. Every `can-interval` seconds, the list of converted frames is sent as a JSON array over the local UDS to the P2P Node, which broadcasts it to the network. This minimizes network packet overhead.
   * **If `--can-interval 0`:** Converted frames are forwarded to the local P2P Node and broadcast immediately, minimizing latency.

---

## 🚀 Sending Data from External Scripts

You can inject data into the P2P network from external scripts (such as test suites, Matlab scripts, or data collectors) using the provided helper function.

### Standard Function: `send_p2p_data`
Defined in [`core/p2p_node.py`](file:///C:/Users/marti/Desktop/STAGE/DEV/core/p2p_node.py#L557), it features cross-platform compatibility:
*   **On Linux (Raspberry Pi):** Communicates with the local active `main_app.py` node via Unix Domain Socket (UDS) `/tmp/p2p_node.sock` to broadcast the data.
*   **On Windows (or Standalone):** Bypasses UDS and directly broadcasts the message to the TCP ports of all peers listed in `peers.json`.

### Example script:
```python
import sys
import os

# Add parent directory of core to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.p2p_node import send_p2p_data

# Data payload to send
payload = {
    "type": "EXTERNAL_COMMAND",
    "target_power_setpoint": 1200.0
}

# Send the data to the P2P network
success = send_p2p_data(payload, target=None)
if success:
    print("Message sent to P2P network!")
```

For a concrete, runnable example, check [`apps/send_data_example.py`](file:///C:/Users/marti/Desktop/STAGE/DEV/apps/send_data_example.py).
