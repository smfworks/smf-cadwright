"""Lightweight SVG preview of a mesh — isometric, shaded, dependency-free.

Projects triangles to 2D with a classic isometric view, shades each face by its
angle to a fixed light, sorts back-to-front (painter's algorithm), and emits an
SVG. SVG renders inline in the chat UI and in browsers, so we get a real preview
without a 3D rasterizer or any third-party library.
"""
from __future__ import annotations

import math

from .mesh import Mesh, Vec3, _normal

# Isometric basis: rotate -45° about Z then tilt. Precomputed screen projection.
_COS30 = math.cos(math.radians(30))
_SIN30 = math.sin(math.radians(30))
_LIGHT = (0.4, -0.3, 0.86)        # normalized-ish light direction


def _project(v: Vec3) -> tuple[float, float, float]:
    x, y, z = v
    sx = (x - y) * _COS30
    sy = (x + y) * _SIN30 - z
    depth = x + y + z             # painter's-algorithm key
    return sx, sy, depth


def _shade(n: Vec3) -> int:
    d = max(0.0, n[0] * _LIGHT[0] + n[1] * _LIGHT[1] + n[2] * _LIGHT[2])
    return int(60 + 175 * d)      # grayscale 60..235


def to_svg(mesh: Mesh, width: int = 640, height: int = 480,
           accent: str = "#3b82f6") -> str:
    if mesh.is_empty():
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                f'height="{height}"><text x="20" y="30">(empty model)</text></svg>')

    faces = []
    for a, b, c in mesh.triangles:
        va, vb, vc = mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]
        pa, pb, pc = _project(va), _project(vb), _project(vc)
        depth = (pa[2] + pb[2] + pc[2]) / 3
        shade = _shade(_normal(va, vb, vc))
        faces.append((depth, (pa, pb, pc), shade))
    faces.sort(key=lambda f: f[0])        # far first

    xs = [p[0] for _, tri, _ in faces for p in tri]
    ys = [p[1] for _, tri, _ in faces for p in tri]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny) or 1.0
    pad = 0.08 * span
    scale = (min(width, height) - 2 * pad * (min(width, height) / span)) / span

    def sx(x): return (x - minx) * scale + (width - (maxx - minx) * scale) / 2
    def sy(y): return (y - miny) * scale + (height - (maxy - miny) * scale) / 2

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
             f'height="{height}" viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="#0f172a"/>']
    for _, (pa, pb, pc), shade in faces:
        col = f"rgb({shade},{shade},{min(255, shade + 12)})"
        pts = f"{sx(pa[0]):.1f},{sy(pa[1]):.1f} {sx(pb[0]):.1f},{sy(pb[1]):.1f} {sx(pc[0]):.1f},{sy(pc[1]):.1f}"
        parts.append(f'<polygon points="{pts}" fill="{col}" stroke="{accent}" '
                     f'stroke-width="0.4" stroke-opacity="0.25"/>')
    parts.append("</svg>")
    return "".join(parts)


def write_svg(mesh: Mesh, path: str, **kw) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_svg(mesh, **kw))
    return path
