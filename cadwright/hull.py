"""3D convex hull (incremental) — our own implementation, stdlib only.

Used by OpenSCAD-style ``hull()``: the convex hull of all child geometry. Common
for rounded/organic parts (e.g. hull of spheres at the corners of a box).
Returns a closed triangle Mesh; returns an empty Mesh if the points are
degenerate (fewer than 4 non-coplanar points).
"""
from __future__ import annotations

from .mesh import Mesh, Vec3

EPS = 1e-7


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _d2(a, b):
    d = _sub(a, b)
    return _dot(d, d)


def _line_dist2(p, a, b):
    ab = _sub(b, a)
    n = _cross(ab, _sub(p, a))
    denom = _dot(ab, ab) or 1.0
    return _dot(n, n) / denom


def _normal(pts, a, b, c) -> Vec3:
    return _cross(_sub(pts[b], pts[a]), _sub(pts[c], pts[a]))


def _oriented(pts, a, b, c, interior) -> tuple[int, int, int]:
    """Order (a,b,c) so the normal points away from the interior point."""
    n = _normal(pts, a, b, c)
    if _dot(n, _sub(interior, pts[a])) > 0:    # normal faces interior -> flip
        return (a, c, b)
    return (a, b, c)


def convex_hull(points: list[Vec3]) -> Mesh:
    seen = set()
    pts: list[Vec3] = []
    for p in points:
        key = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
        if key not in seen:
            seen.add(key)
            pts.append((float(p[0]), float(p[1]), float(p[2])))
    if len(pts) < 4:
        return Mesh()

    i0 = 0
    i1 = max(range(len(pts)), key=lambda i: _d2(pts[i], pts[i0]))
    if _d2(pts[i1], pts[i0]) < EPS:
        return Mesh()
    i2 = max(range(len(pts)), key=lambda i: _line_dist2(pts[i], pts[i0], pts[i1]))
    if _line_dist2(pts[i2], pts[i0], pts[i1]) < EPS:
        return Mesh()
    n = _normal(pts, i0, i1, i2)
    i3 = max(range(len(pts)), key=lambda i: abs(_dot(n, _sub(pts[i], pts[i0]))))
    if abs(_dot(n, _sub(pts[i3], pts[i0]))) < EPS:
        return Mesh()                          # all coplanar -> no volume

    interior = tuple(sum(pts[i][k] for i in (i0, i1, i2, i3)) / 4 for k in range(3))
    faces = [
        _oriented(pts, i0, i1, i2, interior),
        _oriented(pts, i0, i1, i3, interior),
        _oriented(pts, i0, i2, i3, interior),
        _oriented(pts, i1, i2, i3, interior),
    ]

    done = {i0, i1, i2, i3}
    for pi in range(len(pts)):
        if pi in done:
            continue
        p = pts[pi]
        visible = [f for f in faces
                   if _dot(_normal(pts, *f), _sub(p, pts[f[0]])) > EPS]
        if not visible:
            continue
        vis_edges: dict[tuple[int, int], int] = {}
        for (a, b, c) in visible:
            for e in ((a, b), (b, c), (c, a)):
                vis_edges[e] = vis_edges.get(e, 0) + 1
        horizon = [(a, b) for (a, b) in vis_edges if (b, a) not in vis_edges]
        vis_id = {id(f) for f in visible}
        faces = [f for f in faces if id(f) not in vis_id]
        for (a, b) in horizon:
            faces.append(_oriented(pts, a, b, pi, interior))

    # compact vertices actually used
    used = sorted({i for f in faces for i in f})
    remap = {old: new for new, old in enumerate(used)}
    verts = [pts[i] for i in used]
    tris = [(remap[a], remap[b], remap[c]) for (a, b, c) in faces]
    return Mesh(verts, tris)
