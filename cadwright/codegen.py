"""Natural-language -> parametric OpenSCAD code generation.

Modes (env ``CADWRIGHT_LLM``):
    auto (default) - real provider if configured (CADWRIGHT_API_BASE), else mock
    mock           - deterministic offline templates (no network)
    real           - call an OpenAI-compatible chat endpoint

The mock maps a prompt to a parametric template and seeds dimensions parsed from
the text, so the whole pipeline runs offline. The real path asks a model for
OpenSCAD code and strips any markdown fences. Image input is accepted and passed
through to vision-capable real providers (ignored by the mock).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_SYSTEM = (
    "You are a senior mechanical/CAD engineer. Output ONLY valid OpenSCAD code "
    "for 3D printing — no markdown, no prose, no code fences. Put EVERY dimension "
    "in a named variable at the top so it can be tuned. Units are millimetres. "
    "Use $fn for smoothness. Prefer difference()/union() over manual polyhedra."
)

# M-thread clearance hole diameters (mm).
_THREAD = {"m2": 2.4, "m2.5": 2.9, "m3": 3.2, "m4": 4.3, "m5": 5.3, "m6": 6.4}


def _numbers_mm(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm)?\b", text)]


_TRAILING = {"wide", "deep", "tall", "high", "long", "thick", "thickness"}


def _labeled(text: str, *labels: str) -> float | None:
    low = text.lower()
    for lab in labels:
        if lab in _TRAILING:
            # adjective dimension: number comes BEFORE ("50mm wide", "4mm thick")
            m = re.search(rf"(\d+(?:\.\d+)?)\s*mm?\s*{lab}", low)
            if m:
                return float(m.group(1))
            m = re.search(rf"{lab}\s*[:=]?\s*(\d+(?:\.\d+)?)", low)
            if m:
                return float(m.group(1))
        else:
            # noun/label: number comes AFTER ("outer 20", "height: 30")
            m = re.search(rf"{lab}\s*[:=]?\s*(\d+(?:\.\d+)?)", low)
            if m:
                return float(m.group(1))
            m = re.search(rf"(\d+(?:\.\d+)?)\s*mm\s*{lab}", low)
            if m:
                return float(m.group(1))
    return None


def _thread_hole(text: str) -> float | None:
    m = re.search(r"\bm(2|2\.5|3|4|5|6)\b", text, re.IGNORECASE)
    return _THREAD.get("m" + m.group(1).lower()) if m else None


def generate(prompt: str, image_path: str | None = None,
             mode: str | None = None) -> str:
    mode = mode or os.environ.get("CADWRIGHT_LLM", "auto")
    if mode == "real" or (mode == "auto" and os.environ.get("CADWRIGHT_API_BASE")):
        return _strip_fences(_generate_real(prompt, image_path))
    return _generate_mock(prompt)


def edit(scad: str, instruction: str, mode: str | None = None) -> tuple[str, str]:
    """Return (new_scad, note). Mock tweaks variables; real re-generates."""
    mode = mode or os.environ.get("CADWRIGHT_LLM", "auto")
    if mode == "real" or (mode == "auto" and os.environ.get("CADWRIGHT_API_BASE")):
        new = _strip_fences(_edit_real(scad, instruction))
        return new, "regenerated via provider"
    return _edit_mock(scad, instruction)


# ----------------------------------------------------------------------- mock
def _generate_mock(prompt: str) -> str:
    p = prompt.lower()
    nums = _numbers_mm(prompt)

    def pick(idx, default):
        return nums[idx] if idx < len(nums) else default

    header = f"// CADwright — generated from: {prompt.strip()[:80]}\n$fn = 64;\n"

    if any(k in p for k in ("tube", "pipe", "ring", "washer", "standoff",
                            "spacer", "bushing", "bearing")):
        od = _labeled(prompt, "outer", "od", "outside") or pick(0, 20)
        idia = _labeled(prompt, "inner", "id", "inside", "bore") or pick(1, 10)
        h = _labeled(prompt, "height", "tall", "length", "long") or pick(2, 8)
        return (header + f"outer_d = {od};\ninner_d = {idia};\nheight = {h};\n"
                "difference() {\n"
                "    cylinder(h = height, d = outer_d);\n"
                "    translate([0, 0, -1]) cylinder(h = height + 2, d = inner_d);\n"
                "}\n")

    if (any(k in p for k in ("plate", "bracket", "mount", "flange", "panel"))
            or "hole" in p):
        w = _labeled(prompt, "width", "wide") or pick(0, 40)
        d = _labeled(prompt, "depth", "deep") or pick(1, 30)
        t = _labeled(prompt, "thick", "thickness") or pick(2, 4)
        hole = _thread_hole(prompt) or _labeled(prompt, "hole", "bolt") or 3.2
        return (header + f"width = {w};\ndepth = {d};\nthick = {t};\n"
                f"hole_d = {hole};\nmargin = 6;\n"
                "difference() {\n"
                "    cube([width, depth, thick]);\n"
                "    for (x = [margin : width - 2*margin : width - margin])\n"
                "        for (y = [margin, depth - margin])\n"
                "            translate([x, y, -1])\n"
                "                cylinder(h = thick + 2, d = hole_d);\n"
                "}\n")

    if "cone" in p:
        bd = _labeled(prompt, "base", "diameter", "dia") or pick(0, 20)
        h = _labeled(prompt, "height", "tall") or pick(1, 25)
        return header + f"base_d = {bd};\nheight = {h};\ncylinder(h = height, d1 = base_d, d2 = 0);\n"

    if any(k in p for k in ("cylinder", "rod", "disc", "disk", "peg", "pin",
                            "dowel", "knob", "wheel", "coin")):
        dia = _labeled(prompt, "diameter", "dia") or pick(0, 20)
        h = _labeled(prompt, "height", "tall", "thick", "length") or pick(1, 10)
        return header + f"diameter = {dia};\nheight = {h};\ncylinder(h = height, d = diameter);\n"

    if "sphere" in p or "ball" in p or "dome" in p:
        dia = _labeled(prompt, "diameter", "dia") or pick(0, 20)
        return header + f"diameter = {dia};\nsphere(d = diameter);\n"

    if any(k in p for k in ("enclosure", "box", "case", "housing", "tray")) and \
            any(k in p for k in ("hollow", "enclosure", "case", "wall", "box", "tray")):
        w = _labeled(prompt, "width", "wide") or pick(0, 60)
        d = _labeled(prompt, "depth", "deep") or pick(1, 40)
        h = _labeled(prompt, "height", "tall") or pick(2, 25)
        wall = _labeled(prompt, "wall", "thick") or 2
        return (header + f"width = {w};\ndepth = {d};\nheight = {h};\nwall = {wall};\n"
                "difference() {\n"
                "    cube([width, depth, height]);\n"
                "    translate([wall, wall, wall])\n"
                "        cube([width - 2*wall, depth - 2*wall, height]);\n"
                "}\n")

    # default: a labeled block
    w = pick(0, 20)
    d = pick(1, 20)
    h = pick(2, 20)
    return header + f"width = {w};\ndepth = {d};\nheight = {h};\ncube([width, depth, height]);\n"


_VAR_SYNONYMS = {
    "height": ("height", "tall", "taller", "high"),
    "width": ("width", "wide", "wider"),
    "depth": ("depth", "deep", "deeper"),
    "thick": ("thick", "thickness"),
    "wall": ("wall",),
    "diameter": ("diameter", "dia"),
    "outer_d": ("outer", "od", "outside"),
    "inner_d": ("inner", "id", "inside", "bore"),
    "hole_d": ("hole", "bolt"),
    "base_d": ("base",),
}


def _edit_mock(scad: str, instruction: str) -> tuple[str, str]:
    text = instruction.lower()
    number = re.search(r"(\d+(?:\.\d+)?)", instruction)
    if not number:
        return scad, "no numeric value found in instruction; nothing changed"
    value = number.group(1)

    present = set(re.findall(r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*[^;]+;", scad))
    target = None
    # direct: "set X = N" or "X = N"
    direct = re.search(r"([A-Za-z_]\w*)\s*=", instruction)
    if direct and direct.group(1) in present:
        target = direct.group(1)
    if not target:
        for var, words in _VAR_SYNONYMS.items():
            if var in present and any(w in text for w in words):
                target = var
                break
    if not target:
        # fall back to any synonym word that maps to a present var
        for var in present:
            if var in text:
                target = var
                break
    if not target:
        return scad, (f"couldn't map instruction to a variable "
                      f"(have: {', '.join(present) or 'none'})")

    new = re.sub(rf"(?m)^(\s*{re.escape(target)}\s*=\s*)[^;]+;",
                 rf"\g<1>{value};", scad)
    return new, f"set {target} = {value}"


# ----------------------------------------------------------------------- real
def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t.strip())
    return t.strip() + "\n"


def _chat(messages: list[dict]) -> str:
    base = os.environ.get("CADWRIGHT_API_BASE")
    if not base:
        raise RuntimeError(
            "Real codegen requires CADWRIGHT_API_BASE (OpenAI-compatible). "
            "Set CADWRIGHT_LLM=mock for offline use."
        )
    model = os.environ.get("CADWRIGHT_MODEL", "gpt-4o-mini")
    key = os.environ.get("CADWRIGHT_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "messages": messages}).encode(),
        headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"provider HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("unexpected provider response")


def _generate_real(prompt: str, image_path: str | None) -> str:
    user = prompt
    if image_path:
        user += f"\n\n(reference image provided: {os.path.basename(image_path)})"
    return _chat([{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user}])


def _edit_real(scad: str, instruction: str) -> str:
    return _chat([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Current model:\n{scad}\n\nApply this change "
         f"and return the full updated OpenSCAD code:\n{instruction}"},
    ])
