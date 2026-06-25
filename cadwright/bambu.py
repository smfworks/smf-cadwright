"""Bambu Lab printer integration — upload 3MF via FTPS, start print via MQTT.

    from .bambu import BambuPrinter

    printer = BambuPrinter(host="192.168.1.62", access_code="12345678")
    info = printer.get_version()        # check connectivity
    printer.upload_3mf("model.3mf")     # upload to SD card
    printer.start_print("model.3mf")    # start the print

Requires:
    - pip install paho-mqtt   (MQTT over TLS)
    - ftplib from stdlib       (FTPS upload)

The printer's LAN access code is the 8-digit code shown on the printer's
LCD: Settings → Network → LAN Access Code.  Both LAN Mode and Developer Mode
must be enabled on the printer for control commands (MQTT writes) to work.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import time
from ftplib import FTP_TLS, error_perm
from pathlib import Path
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # paho-mqtt is optional — only needed for print control


class BambuError(Exception):
    """Bambu printer communication error."""


class BambuPrinter:
    """Lightweight Bambu Lab LAN client (FTPS upload + MQTT control)."""

    def __init__(
        self,
        host: str,
        access_code: str,
        port_mqtt: int = 8883,
        port_ftps: int = 990,
        username: str = "bblp",
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.access_code = access_code
        self.port_mqtt = port_mqtt
        self.port_ftps = port_ftps
        self.username = username
        self.timeout = timeout
        self._seq = 0
        self._serial: str | None = None

    # ── Discovery / info ───────────────────────────────────────────

    def _next_seq(self) -> str:
        self._seq += 1
        return str(self._seq)

    def get_serial(self) -> str:
        """Discover the printer's serial number via MQTT get_version."""
        if self._serial:
            return self._serial
        info = self.get_version()
        for mod in info.get("module", []):
            if mod.get("name") == "rv1126" and mod.get("sn"):
                self._serial = mod["sn"]
                return self._serial
        raise BambuError("Could not determine printer serial from get_version")

    def get_version(self) -> dict:
        """Send info.get_version over MQTT, return the response."""
        resp = self._mqtt_request(
            {"info": {"sequence_id": "0", "command": "get_version"}}
        )
        return resp.get("info", {})

    def get_status(self) -> dict:
        """Send pushing.pushall, return the full printer status."""
        resp = self._mqtt_request(
            {
                "pushing": {
                    "sequence_id": "0",
                    "command": "pushall",
                    "version": 1,
                    "push_target": 1,
                }
            }
        )
        return resp.get("print", {})

    # ── File upload (FTPS) ──────────────────────────────────────────

    def upload_3mf(self, local_path: str, remote_dir: str = "/") -> str:
        """Upload a .3mf file to the printer's SD card via FTPS.

        Returns the full remote path on the printer (e.g. /model.3mf).
        """
        path = Path(local_path)
        if not path.exists():
            raise BambuError(f"File not found: {local_path}")
        if path.suffix.lower() != ".3mf":
            raise BambuError("Only .3mf files can be uploaded to Bambu printers")

        remote_name = path.name
        remote_path = f"{remote_dir.rstrip('/')}/{remote_name}"

        ftp = self._ftps_connect()
        try:
            # Ensure we're in the right directory
            try:
                ftp.cwd(remote_dir)
            except error_perm:
                pass  # root or already there

            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
        finally:
            ftp.quit()

        return remote_path

    # ── Print control (MQTT) ────────────────────────────────────────

    def start_print(self, remote_path: str, plate_idx: int = 1) -> dict:
        """Tell the printer to start printing a file already on its SD card.

        remote_path: absolute path on the printer (e.g. /model.3mf)
        plate_idx: which plate/plate index to print (default 1)
        """
        payload = {
            "print": {
                "sequence_id": self._next_seq(),
                "command": "project_file",
                "param": "Metadata/plate_1.gcode",
                "project_id": "0",
                "profile_id": "0",
                "subtask_id": "0",
                "task_id": "0",
                "subtask_name": os.path.basename(remote_path),
                "file": remote_path,
                "url": f"file://{remote_path}",
                "md5": "",
                "timelapse": False,
                "bed_type": "auto",
                "bed_levelling": True,
                "flow_cali": True,
                "vibration_cali": True,
                "layer_inspect": True,
                "record_ams": False,
                "use_ams": False,
            }
        }
        return self._mqtt_request(payload)

    def stop_print(self) -> dict:
        """Stop the current print."""
        return self._mqtt_request(
            {"print": {"sequence_id": self._next_seq(), "command": "stop", "param": ""}}
        )

    def pause_print(self) -> dict:
        """Pause the current print."""
        return self._mqtt_request(
            {"print": {"sequence_id": self._next_seq(), "command": "pause", "param": ""}}
        )

    def resume_print(self) -> dict:
        """Resume the current print."""
        return self._mqtt_request(
            {"print": {"sequence_id": self._next_seq(), "command": "resume", "param": ""}}
        )

    def set_speed(self, level: int) -> dict:
        """Set print speed. 1=silent, 2=standard, 3=sport, 4=ludicrous."""
        if level not in (1, 2, 3, 4):
            raise BambuError(f"Invalid speed level: {level} (must be 1-4)")
        return self._mqtt_request(
            {
                "print": {
                    "sequence_id": self._next_seq(),
                    "command": "print_speed",
                    "param": str(level),
                }
            }
        )

    def home(self) -> dict:
        """Home all axes (G28)."""
        return self._mqtt_request(
            {
                "print": {
                    "sequence_id": self._next_seq(),
                    "command": "gcode_line",
                    "param": "G28",
                }
            }
        )

    # ── Combined convenience ───────────────────────────────────────

    def upload_and_print(
        self, local_path: str, remote_dir: str = "/", plate_idx: int = 1
    ) -> dict:
        """Upload a 3MF and immediately start printing it.

        Returns the MQTT response from the start_print command.
        """
        remote = self.upload_3mf(local_path, remote_dir)
        # Give the printer a moment to register the file on the SD card
        time.sleep(1)
        return self.start_print(remote, plate_idx)

    # ── Internals: FTPS ─────────────────────────────────────────────

    def _ftps_connect(self) -> FTP_TLS:
        """Connect to the printer's FTPS server (implicit TLS, port 990)."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        ftp = FTP_TLS()
        ftp.ssl_version = ssl.PROTOCOL_TLS_CLIENT
        ftp.context = ctx
        ftp.connect(self.host, self.port_ftps, timeout=self.timeout)
        ftp.login(self.username, self.access_code)
        ftp.prot_p()  # switch to secure data connection
        return ftp

    # ── Internals: MQTT ─────────────────────────────────────────────

    def _mqtt_request(self, payload: dict, wait: float = 5.0) -> dict:
        """Send a single MQTT request and wait for the matching response.

        Uses a connect-per-op pattern: connect, subscribe, publish, wait
        for the ACK, disconnect. Simple and safe.
        """
        if mqtt is None:
            raise BambuError(
                "paho-mqtt not installed. Run: pip install paho-mqtt"
            )

        serial = self.get_serial() if payload.get("print") else None
        # For info/pushing requests we need the serial too for the topic
        if not serial:
            # First call — we need serial for topic routing, but get_version
            # itself needs the topic. Bootstrapping: use a wildcard subscribe.
            serial = self._get_serial_bootstrap()

        request_topic = f"device/{serial}/request"
        report_topic = f"device/{serial}/report"

        result: dict[str, Any] = {}
        done = {"flag": False}

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        client = mqtt.Client(
            client_id=f"cadwright-{os.getpid()}-{int(time.time())}",
            clean_session=True,
        )
        client.username_pw_set(self.username, self.access_code)
        client.tls_set_context(ctx)

        def on_connect(c, userdata, flags, rc, properties=None):
            c.subscribe(report_topic)

        def on_message(c, userdata, msg):
            nonlocal result
            try:
                data = json.loads(msg.payload.decode("utf-8"))
            except json.JSONDecodeError:
                return
            # Check if this is the response to our command
            req_cat = next(iter(payload.keys()))
            if req_cat in data:
                resp = data[req_cat]
                req_seq = payload[req_cat].get("sequence_id", "0")
                if (
                    resp.get("sequence_id") == req_seq
                    and resp.get("result") is not None
                ):
                    result = data
                    done["flag"] = True

        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(self.host, self.port_mqtt, keepalive=30)
        client.loop_start()

        try:
            # Wait for connection + subscription
            time.sleep(0.5)
            client.publish(request_topic, json.dumps(payload), qos=1)

            deadline = time.time() + wait
            while time.time() < deadline and not done["flag"]:
                time.sleep(0.1)

            if not done["flag"]:
                # Return any data we received even without a matching ACK
                if result:
                    return result
                raise BambuError(
                    f"No response from printer within {wait}s "
                    f"(check: LAN Mode ON, Developer Mode ON, access code correct)"
                )
        finally:
            client.loop_stop()
            client.disconnect()

        return result

    def _get_serial_bootstrap(self) -> str:
        """Get serial via a wildcard subscription (for first command)."""
        if self._serial:
            return self._serial

        if mqtt is None:
            raise BambuError("paho-mqtt not installed")

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        client = mqtt.Client(
            client_id=f"cadwright-boot-{int(time.time())}",
            clean_session=True,
        )
        client.username_pw_set(self.username, self.access_code)
        client.tls_set_context(ctx)

        serial_holder: list[str] = []

        def on_connect(c, userdata, flags, rc, properties=None):
            c.subscribe("device/+/report")

        def on_message(c, userdata, msg):
            try:
                data = json.loads(msg.payload.decode("utf-8"))
            except json.JSONDecodeError:
                return
            if "info" in data:
                for mod in data["info"].get("module", []):
                    if mod.get("name") == "rv1126" and mod.get("sn"):
                        serial_holder.append(mod["sn"])
                        break

        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(self.host, self.port_mqtt, keepalive=30)
        client.loop_start()

        try:
            # Send get_version on a wildcard topic
            time.sleep(0.5)
            payload = {"info": {"sequence_id": "0", "command": "get_version"}}
            # Publish to a device-specific topic — but we don't know serial yet
            # Use the fact that the printer listens on device/{serial}/request
            # We need to discover serial another way: SSDP or port 9999
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass

        # Fallback: get serial via the Bambu discovery protocol (port 9999)
        serial = self._get_serial_via_discovery()
        self._serial = serial
        return serial

    def _get_serial_via_discovery(self) -> str:
        """Get printer serial number via the Bambu discovery protocol (port 9999).

        The printer responds to a JSON request on TCP 9999 with device info
        including the serial number.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, 9999))

            # Bambu discovery: send a simple info request
            request = json.dumps({"cmd": {"info": {}}})
            sock.sendall(request.encode("utf-8"))

            time.sleep(0.5)
            data = sock.recv(4096)
            sock.close()

            resp = json.loads(data.decode("utf-8"))
            info = resp.get("info", {})
            serial = info.get("sn", "")
            if serial:
                self._serial = serial
                return serial

            raise BambuError("Could not discover printer serial number")
        except (socket.error, json.JSONDecodeError, KeyError) as e:
            raise BambuError(f"Failed to discover printer serial: {e}")