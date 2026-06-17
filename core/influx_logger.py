import os
import time
import re

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUXDB_CLIENT_AVAILABLE = True
except ImportError:
    INFLUXDB_CLIENT_AVAILABLE = False

class InfluxDBLogger:
    def __init__(self):
        # We enable it if the environment variable INFLUXDB_ENABLED is true
        self.enabled = os.environ.get("INFLUXDB_ENABLED", "false").lower() in ("true", "1", "yes")
        if not self.enabled:
            return
            
        if not INFLUXDB_CLIENT_AVAILABLE:
            print("[!] Warning: INFLUXDB_ENABLED=true but 'influxdb-client' is not installed.")
            print("[!] Run: pip install influxdb-client")
            self.enabled = False
            return

        self.url = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.environ.get("INFLUXDB_TOKEN", "l2ep_secret_token")
        self.org = os.environ.get("INFLUXDB_ORG", "l2ep")
        self.bucket = os.environ.get("INFLUXDB_BUCKET", "ems_testbench")
        
        try:
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            print(f"[*] InfluxDB Logger initialized. Writing to {self.url} (Bucket: {self.bucket})")
        except Exception as e:
            print(f"[!] Error initializing InfluxDB client: {e}")
            self.enabled = False

    def log_message(self, sender_id, content):
        if not self.enabled:
            return

        try:
            fields = {}
            # Case 1: content is a dict
            if isinstance(content, dict):
                # Check if it's a CAN frame (simulated or real)
                if content.get("type") == "CAN_FRAME" and "data" in content:
                    data_str = str(content["data"])
                    v_match = re.search(r"V:([\d\.]+)", data_str)
                    soc_match = re.search(r"SOC:([\d\.]+)", data_str)
                    p_match = re.search(r"P:([\d\.-]+)", data_str)
                    
                    if v_match:
                        fields["voltage"] = float(v_match.group(1))
                    if soc_match:
                        fields["soc"] = float(soc_match.group(1))
                    if p_match:
                        fields["power"] = float(p_match.group(1))
                else:
                    # Generic dictionary fields (e.g. power, soc, voltage from JSON telemetry)
                    for k, v in content.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            fields[k] = float(v)
            
            if not fields:
                return

            point = Point("battery_metrics") \
                .tag("node_id", sender_id)
            
            for k, v in fields.items():
                point = point.field(k, v)
                
            # Write to InfluxDB
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            
        except Exception as e:
            print(f"[!] InfluxDB write error: {e}")

    def shutdown(self):
        if self.enabled and hasattr(self, "client"):
            try:
                self.client.close()
            except Exception:
                pass
