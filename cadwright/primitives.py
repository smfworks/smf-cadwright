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
    sectors = _fn(fn)
    stacks = max(2, sectors // 2)
    verts: list[Vec3] = []
    tris = []

    # Latitude rings i = 1..stacks-1 (the poles are single apex vertices).
    ring_base = {}
    for i in range(1, stacks):
        phi = math.pi * i / stacks
        z = r * math.cos(phi)
        rr = r * math.sin(phi)
        ring_base[i] = len(verts)
        for j in range(sectors):
            theta = 2 * math.pi * j / sectors
            verts.append((rr * math.cos(theta), rr * math.sin(theta), z))

    top = len(verts); verts.append((0.0, 0.0, r))
    bot = len(verts); verts.append((0.0, 0.0, -r))

    b1 = ring_base[1]
    for j in range(sectors):                 # top cap
        jn = (j + 1) % sectors
        tris.append((top, b1 + j, b1 + jn))
    bk = ring_base[stacks - 1]
    for j in range(sectors):                 # bottom cap
        jn = (j + 1) % sectors
        tris.append((bot, bk + jn, bk + j))
    for i in range(1, stacks - 1):           # bands between rings
        a, b = ring_base[i], ring_base[i + 1]
        for j in range(sectors):
            jn = (j + 1) % sectors
            tris.append((a + j, a + jn, b + jn))
            tris.append((a + j, b + jn, b + j))

    # Orient every face outward (convex shape centred at origin): if a triangle's
    # normal points toward the centre, swap its winding.
    fixed = []
    for (ia, ib, ic) in tris:
        va, vb, vc = verts[ia], verts[ib], verts[ic]
        n = _sphere_normal(va, vb, vc)
        cx = (va[0] + vb[0] + vc[0]) / 3
        cy = (va[1] + vb[1] + vc[1]) / 3
        cz = (va[2] + vb[2] + vc[2]) / 3
        if n[0] * cx + n[1] * cy + n[2] * cz < 0:
            fixed.append((ia, ic, ib))
        else:
            fixed.append((ia, ib, ic))
    return Mesh(verts, fixed)


def _sphere_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def polyhedron(points: list, faces: list) -> Mesh:
    verts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    n = len(verts)
    tris = []
    for face in faces:
        for idx in face:
            if int(idx) < 0 or int(idx) >= n:
                raise ValueError(
                    f"polyhedron face index {idx} out of range 0..{n - 1}")
        for i in range(1, len(face) - 1):       # fan-triangulate each face
            tris.append((int(face[0]), int(face[i]), int(face[i + 1])))
    return Mesh(verts, tris)
