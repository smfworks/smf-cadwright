"""2D profiles and linear extrusion.

A 2D shape is just a closed outline: an ordered list of (x, y) points (CCW).
``square``/``circle``/``polygon`` build outlines; ``extrude`` turns an outline
into a 3D prism (with optional centering and twist). Cap triangulation is a fan,
so concave outlines extrude correctly along the walls but cap best on convex
profiles — the documented limitation for v0.
"""
from __future__ import annotations

import math

from .mesh import Mesh, Vec3

Pt2 = tuple[float, float]


def square(size=1.0, center: bool = False) -> list[Pt2]:
    if isinstance(size, (int, float)):
        sx = sy = float(size)
    else:
        sx, sy = float(size[0]), float(size[1])
    ox, oy = (-sx / 2, -sy / 2) if center else (0.0, 0.0)
    return [(ox, oy), (ox + sx, oy), (ox + sx, oy + sy), (ox, oy + sy)]


def circle(r=1.0, fn: int = 32) -> list[Pt2]:
    n = max(3, int(fn))
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def polygon(points) -> list[Pt2]:
    return [(float(p[0]), float(p[1])) for p in points]


def transform2d(name: str, vec, outline: list[Pt2]) -> list[Pt2]:
    if name == "translate":
        vx, vy = (vec[0], vec[1]) if isinstance(vec, list) else (vec, vec)
        return [(x + vx, y + vy) for x, y in outline]
    if name == "scale":
        if isinstance(vec, list):
            sx = vec[0]
            sy = vec[1] if len(vec) > 1 else vec[0]
        else:
            sx = sy = vec
        return [(x * sx, y * sy) for x, y in outline]
    if name == "rotate":
        ang = math.radians(vec[0] if isinstance(vec, list) else vec)
        c, s = math.cos(ang), math.sin(ang)
        return [(x * c - y * s, x * s + y * c) for x, y in outline]
    return outline


def extrude(outline: list[Pt2], height: float, center: bool = False,
            twist: float = 0.0, slices: int | None = None) -> Mesh:
    n = len(outline)
    if n < 3:
        return Mesh()
    height = float(height)
    z0, z1 = (-height / 2, height / 2) if center else (0.0, height)
    if twist == 0.0:
        slices = 1
    else:
        slices = slices or max(2, int(abs(twist) / 15) + 1)

    verts: list[Vec3] = []
    rings = []
    for k in range(slices + 1):
        t = k / slices
        z = z0 + (z1 - z0) * t
        ang = math.radians(twist * t)
        c, s = math.cos(ang), math.sin(ang)
        base = len(verts)
        for x, y in outline:
            verts.append((x * c - y * s, x * s + y * c, z))
        rings.append(base)

    tris = []
    for k in range(slices):                  # side walls
        b0, b1 = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            tris.append((b0 + i, b0 + j, b1 + j))
            tris.append((b0 + i, b1 + j, b1 + i))
    b0 = rings[0]                            # bottom cap (faces -z)
    for i in range(1, n - 1):
        tris.append((b0, b0 + i + 1, b0 + i))
    bt = rings[-1]                           # top cap (faces +z)
    for i in range(1, n - 1):
        tris.append((bt, bt + i, bt + i + 1))
    return Mesh(verts, tris)


def revolve(outline: list[Pt2], segments: int = 32) -> Mesh:
    """Revolve a 2D profile a full 360 deg about the Z axis (lathe).

    Profile points are (radius, z); radius should be >= 0. The result is a
    closed surface of revolution (vases, pulleys, bottles).
    """
    n = len(outline)
    if n < 3:
        return Mesh()
    seg = max(3, int(segments))
    verts: list[Vec3] = []
    for s in range(seg):
        theta = 2 * math.pi * s / seg
        c, sn = math.cos(theta), math.sin(theta)
        for x, y in outline:
            r = max(0.0, x)
            verts.append((r * c, r * sn, y))
    tris = []
    for s in range(seg):
        s2 = (s + 1) % seg
        for i in range(n):
            i2 = (i + 1) % n
            a, b = s * n + i, s * n + i2
            d, e = s2 * n + i, s2 * n + i2
            tris.append((a, b, e))
            tris.append((a, e, d))
    return Mesh(verts, tris)


# 5x7 vector font for text() — rows top->bottom, '#' = filled cell.
_FONT: dict[str, list[str]] = {
    " ": ["     "] * 7,
    "A": ["  #  ", " # # ", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ####", "#    ", "#    ", "#  ##", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "J": ["#####", "    #", "    #", "    #", "#   #", "#   #", " ### "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "#   #", "# # #", "## ##", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "2": [" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"],
    "3": ["#####", "    #", "   # ", "  ## ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    "-": ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
    "_": ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
    ":": ["     ", " ##  ", " ##  ", "     ", " ##  ", " ##  ", "     "],
}


def text(s: str, size: float = 10.0, spacing: float = 1.0) -> list[list[Pt2]]:
    """Return a list of square outlines forming blocky text (use in extrude).

    Cells are ``size/7`` mm; characters advance 6 cells * ``spacing``. Unknown
    characters render as a space.
    """
    px = float(size) / 7.0
    rows = 7
    out: list[list[Pt2]] = []
    cursor = 0.0
    for ch in str(s).upper():
        glyph = _FONT.get(ch, _FONT[" "])
        for r, line in enumerate(glyph):
            for c, cell in enumerate(line):
                if cell == "#":
                    x0 = cursor + c * px
                    y0 = (rows - 1 - r) * px
                    out.append([(x0, y0), (x0 + px, y0),
                                (x0 + px, y0 + px), (x0, y0 + px)])
        cursor += 6 * px * float(spacing)
    return out
