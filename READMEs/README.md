# L2EP_EMS_BENCH
Group of libraries and programs for reception and transmission of messages on different buses of communication (CAN, TCP/IP, ZMQ).

## Core Configuration & Files

* **`peers.json`**: Stores historically discovered peer addresses (`ID:IP:PORT`). When connections are lost, nodes time out in memory to avoid redundant operations, but their addresses are safely preserved (merged rather than overwritten) in `peers.json` so they remain discoverable on subsequent restarts.
* **`data-sent.json`**: A local JSON file containing the node's current battery telemetry (e.g., `power`, `soc`, `voltage`) to be broadcast to all peers.
* **`data-recieved.json`**: Automatically created/updated on each node to store the merged real-time state registry dictionary of all peers.

## How to Run

1. **Configure Telemetry:**
   Create or modify `data-sent.json` in your execution directory (e.g. `DEV/`):
   ```json
   {
       "power": 1500.0,
       "soc": 75.0,
       "voltage": 48.0
   }
   ```
2. **Launch Node:**
   Run the main application:
   ```bash
   python main_app.py
   ```
   Every 10 seconds, the node reads `data-sent.json` and broadcasts its contents to all peers. When other nodes receive this message, they merge and log the data in `data-recieved.json`.

