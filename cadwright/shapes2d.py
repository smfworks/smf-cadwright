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
