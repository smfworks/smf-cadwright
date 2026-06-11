"""Solid primitives -> Mesh (cube, sphere, cylinder/cone, polyhedron).

Geometry and defaults follow OpenSCAD conventions: cube/cylinder sit in the
+octant by default and `center=true` recentres them; `$fn` controls the facet
count of curved surfaces.
"""
from __future__ import annotations

import math

from .mesh import Mesh, Vec3


def cube(size=1.0, center: bool = False) -> Mesh:
    if isinstance(size, (int, float)):
        sx = sy = sz = float(size)
    else:
        sx, sy, sz = (float(size[0]), float(size[1]), float(size[2]))
    ox, oy, oz = (-sx / 2, -sy / 2, -sz / 2) if center else (0.0, 0.0, 0.0)
    v = [
        (ox, oy, oz), (ox + sx, oy, oz), (ox + sx, oy + sy, oz), (ox, oy + sy, oz),
        (ox, oy, oz + sz), (ox + sx, oy, oz + sz), (ox + sx, oy + sy, oz + sz), (ox, oy + sy, oz + sz),
    ]
    # faces with outward winding (CCW seen from outside)
    faces = [
        (0, 3, 2), (0, 2, 1),      # bottom (z-)
        (4, 5, 6), (4, 6, 7),      # top (z+)
        (0, 1, 5), (0, 5, 4),      # front (y-)
        (2, 3, 7), (2, 7, 6),      # back (y+)
        (1, 2, 6), (1, 6, 5),      # right (x+)
        (0, 4, 7), (0, 7, 3),      # left (x-)
    ]
    return Mesh(v, list(faces))


def _fn(fn: int | None, default: int = 32) -> int:
    return max(3, int(fn)) if fn else default


def cylinder(h=1.0, r=None, r1=None, r2=None, center: bool = False,
             fn: int | None = None) -> Mesh:
    if r is not None:
        r1 = r2 = float(r)
    r1 = 0.0 if r1 is None else float(r1)
    r2 = 0.0 if r2 is None else float(r2)
    h = float(h)
    n = _fn(fn)
    z0, z1 = (-h / 2, h / 2) if center else (0.0, h)

    verts: list[Vec3] = []
    tris = []

    def ring(radius, z):
        base = len(verts)
        for i in range(n):
            a = 2 * math.pi * i / n
            verts.append((radius * math.cos(a), radius * math.sin(a), z))
        return base

    if r1 > 0 and r2 > 0:
        b0 = ring(r1, z0)
        b1 = ring(r2, z1)
        for i in range(n):
            j = (i + 1) % n
            tris.append((b0 + i, b0 + j, b1 + j))
            tris.append((b0 + i, b1 + j, b1 + i))
        c0 = len(verts); verts.append((0, 0, z0))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c0, b0 + j, b0 + i))           # bottom cap (faces -z)
        c1 = len(verts); verts.append((0, 0, z1))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c1, b1 + i, b1 + j))           # top cap (faces +z)
    elif r1 > 0 and r2 == 0:                            # cone up
        b0 = ring(r1, z0)
        apex = len(verts); verts.append((0, 0, z1))
        for i in range(n):
            j = (i + 1) % n
            tris.append((b0 + i, b0 + j, apex))
        c0 = len(verts); verts.append((0, 0, z0))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c0, b0 + j, b0 + i))
    elif r1 == 0 and r2 > 0:                            # cone down
        b1 = ring(r2, z1)
        apex = len(verts); verts.append((0, 0, z0))
        for i in range(n):
            j = (i + 1) % n
            tris.append((b1 + j, b1 + i, apex))
        c1 = len(verts); verts.append((0, 0, z1))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c1, b1 + i, b1 + j))
    return Mesh(verts, tris)


def sphere(r=1.0, fn: int | None = None) -> Mesh:
    r = float(r)
    n = _fn(fn)
    rings = max(2, n // 2)          # stacks
    sectors = n                     # slices
    verts: list[Vec3] = []
    tris = []
    for i in range(rings + 1):
        phi = math.pi * i / rings           # 0..pi (north to south)
        z = r * math.cos(phi)
        rr = r * math.sin(phi)
        for j in range(sectors):
            theta = 2 * math.pi * j / sectors
            verts.append((rr * math.cos(theta), rr * math.sin(theta), z))

    def idx(i, j):
        return i * sectors + (j % sectors)

    for i in range(rings):
        for j in range(sectors):
            a = idx(i, j)
            b = idx(i + 1, j)
            c = idx(i + 1, j + 1)
            d = idx(i, j + 1)
            if i != 0:
                tris.append((a, b, c))
            if i != rings - 1:
                tris.append((a, c, d))
    return Mesh(verts, tris)


def polyhedron(points: list, faces: list) -> Mesh:
    verts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    tris = []
    for face in faces:
        for i in range(1, len(face) - 1):       # fan-triangulate each face
            tris.append((int(face[0]), int(face[i]), int(face[i + 1])))
    return Mesh(verts, tris)
