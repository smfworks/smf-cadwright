"""Tests for the Bambu Lab printer integration."""
import json
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadwright.bambu import BambuPrinter, BambuError


# ── Construction ───────────────────────────────────────────────────

class TestConstruction:
    def test_basic_construction(self):
        p = BambuPrinter(host="192.168.1.62", access_code="12345678")
        assert p.host == "192.168.1.62"
        assert p.access_code == "12345678"
        assert p.port_mqtt == 8883
        assert p.port_ftps == 990
        assert p.username == "bblp"

    def test_custom_ports(self):
        p = BambuPrinter(host="10.0.0.5", access_code="abcd1234", port_mqtt=1883, port_ftps=21)
        assert p.port_mqtt == 1883
        assert p.port_ftps == 21


# ── Validation ─────────────────────────────────────────────────────

class TestUploadValidation:
    def test_missing_file(self, tmp_path):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        with pytest.raises(BambuError, match="File not found"):
            p.upload_3mf(str(tmp_path / "nonexistent.3mf"))

    def test_non_3mf_file(self, tmp_path):
        f = tmp_path / "model.stl"
        f.write_text("solid test")
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        with pytest.raises(BambuError, match="Only .3mf files"):
            p.upload_3mf(str(f))


# ── Sequence ID ───────────────────────────────────────────────────

class TestSequenceID:
    def test_sequence_increments(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        assert p._next_seq() == "1"
        assert p._next_seq() == "2"
        assert p._next_seq() == "3"


# ── Speed validation ───────────────────────────────────────────────

class TestSpeedValidation:
    def test_valid_speeds(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={})
        for level in (1, 2, 3, 4):
            p.set_speed(level)
            payload = p._mqtt_request.call_args[0][0]
            assert payload["print"]["command"] == "print_speed"
            assert payload["print"]["param"] == str(level)

    def test_invalid_speed(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        with pytest.raises(BambuError, match="Invalid speed level"):
            p.set_speed(5)
        with pytest.raises(BambuError, match="Invalid speed level"):
            p.set_speed(0)


# ── Start print payload ───────────────────────────────────────────

class TestStartPrint:
    def test_payload_structure(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={"print": {"result": "success"}})
        resp = p.start_print("/test.3mf")
        payload = p._mqtt_request.call_args[0][0]
        assert payload["print"]["command"] == "project_file"
        assert payload["print"]["file"] == "/test.3mf"
        assert "url" in payload["print"]
        assert "file://" in payload["print"]["url"]
        assert resp["print"]["result"] == "success"


# ── Stop / pause / resume payloads ────────────────────────────────

class TestControlPayloads:
    def test_stop_payload(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={})
        p.stop_print()
        payload = p._mqtt_request.call_args[0][0]
        assert payload["print"]["command"] == "stop"
        assert payload["print"]["param"] == ""

    def test_pause_payload(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={})
        p.pause_print()
        payload = p._mqtt_request.call_args[0][0]
        assert payload["print"]["command"] == "pause"

    def test_resume_payload(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={})
        p.resume_print()
        payload = p._mqtt_request.call_args[0][0]
        assert payload["print"]["command"] == "resume"

    def test_home_payload(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._mqtt_request = MagicMock(return_value={})
        p.home()
        payload = p._mqtt_request.call_args[0][0]
        assert payload["print"]["command"] == "gcode_line"
        assert payload["print"]["param"] == "G28"


# ── Mock FTPS upload ──────────────────────────────────────────────

class TestFTPSUpload:
    def test_successful_upload(self, tmp_path):
        f = tmp_path / "test.3mf"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * 100)  # fake 3MF

        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        mock_ftp = MagicMock()
        mock_ftp.storbinary = MagicMock()

        with patch.object(p, "_ftps_connect", return_value=mock_ftp):
            remote = p.upload_3mf(str(f))
            assert remote == "/test.3mf"
            mock_ftp.storbinary.assert_called_once()
            mock_ftp.quit.assert_called_once()


# ── Get version via discovery ─────────────────────────────────────

class TestSerialDiscovery:
    def test_discovery_finds_serial(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        mock_resp = {
            "info": {
                "sn": "A1S12A3B4567",
                "main": {"dev_model_name": "A1"},
            }
        }
        with patch("cadwright.bambu.socket.socket") as mock_sock_class:
            mock_sock = MagicMock()
            mock_sock_class.return_value = mock_sock
            mock_sock.recv.return_value = json.dumps(mock_resp).encode("utf-8")
            serial = p._get_serial_via_discovery()
            assert serial == "A1S12A3B4567"

    def test_serial_cached(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        p._serial = "CACHED123"
        assert p.get_serial() == "CACHED123"


# ── MQTT module not installed ─────────────────────────────────────

class TestMissingDeps:
    def test_mqtt_request_without_paho(self):
        p = BambuPrinter(host="1.2.3.4", access_code="00000000")
        with patch("cadwright.bambu.mqtt", None):
            with pytest.raises(BambuError, match="paho-mqtt not installed"):
                p._mqtt_request({"info": {"sequence_id": "0", "command": "get_version"}})