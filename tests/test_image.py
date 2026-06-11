import base64
import struct

import pytest

from cadwright import codegen


def _png_bytes() -> bytes:
    # Minimal 1x1 PNG (valid signature + IHDR), enough to encode/round-trip.
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return sig + ihdr + b"\x00" * 8


def test_build_messages_text_only():
    msgs = codegen._build_messages("a 20mm cube", None)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["content"] == "a 20mm cube"        # plain string when no image


def test_build_messages_multimodal(tmp_path):
    img = tmp_path / "ref.png"
    img.write_bytes(_png_bytes())
    msgs = codegen._build_messages("model this bracket", str(img))
    content = msgs[1]["content"]
    assert isinstance(content, list)
    kinds = {part["type"] for part in content}
    assert kinds == {"text", "image_url"}
    url = next(p["image_url"]["url"] for p in content if p["type"] == "image_url")
    assert url.startswith("data:image/png;base64,")
    # the base64 payload decodes back to the original bytes
    payload = url.split(",", 1)[1]
    assert base64.b64decode(payload) == _png_bytes()


def test_encode_image_missing_file():
    with pytest.raises(RuntimeError):
        codegen._encode_image("does-not-exist.png")


def test_mock_generate_with_image_still_valid(tmp_path):
    img = tmp_path / "ref.jpg"
    img.write_bytes(_png_bytes())
    scad = codegen.generate("a 30mm cube", image_path=str(img), mode="mock")
    assert "cube" in scad
    assert "offline mock can't analyze" in scad      # honest note, still usable
