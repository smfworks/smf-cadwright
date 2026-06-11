"""Constructive Solid Geometry via BSP trees — our own clean-room implementation.

Implements union / difference / intersection on triangle meshes (the core of
OpenSCAD-style modelling) using binary space partitioning. This is an original
Python implementation of the well-known BSP-CSG technique; it depends on nothing
but the standard library.

Polygons are convex faces (>=3 coplanar vertices). Meshes come in as triangles
and go out as triangles (fan-triangulated).
"""
from __future__ import annotations

import math

from .mesh import Mesh, Vec3

EPSILON = 1e-5

COPLANAR = 0
FRONT = 1
BACK = 2
SPANNING = 3


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


class Plane:
    __slots__ = ("normal", "w")

    def __init__(self, normal: Vec3, w: float):
        self.normal = normal
        self.w = w

    @staticmethod
    def from_points(a: Vec3, b: Vec3, c: Vec3) -> "Plane | None":
        n = _cross(_sub(b, a), _sub(c, a))
        length = math.sqrt(_dot(n, n))
        if length < 1e-12:
            return None                      # degenerate triangle
        n = (n[0] / length, n[1] / length, n[2] / length)
        return Plane(n, _dot(n, a))

    def flip(self) -> None:
        self.normal = (-self.normal[0], -self.normal[1], -self.normal[2])
        self.w = -self.w

    def split_polygon(self, polygon: "Polygon",
                      coplanar_front: list, coplanar_back: list,
                      front: list, back: list) -> None:
        if polygon.plane is None:        # degenerate (collinear) triangle — drop it
            return
        types = []
        polygon_type = 0
        for v in polygon.vertices:
            t = _dot(self.normal, v) - self.w
            ptype = (BACK if t < -EPSILON else FRONT if t > EPSILON else COPLANAR)
            polygon_type |= ptype
            types.append(ptype)

        if polygon_type == COPLANAR:
            (coplanar_front if _dot(self.normal, polygon.plane.normal) > 0
             else coplanar_back).append(polygon)
        elif polygon_type == FRONT:
            front.append(polygon)
        elif polygon_type == BACK:
            back.append(polygon)
        else:  # SPANNING — split the polygon along the plane
            f, b = [], []
            n = len(polygon.vertices)
            for i in range(n):
                j = (i + 1) % n
                ti, tj = types[i], types[j]
                vi, vj = polygon.vertices[i], polygon.vertices[j]
                if ti != BACK:
                    f.append(vi)
                if ti != FRONT:
                    b.append(vi)
                if (ti | tj) == SPANNING:
                    denom = _dot(self.normal, _sub(vj, vi))
                    if abs(denom) > 1e-12:
                        t = (self.w - _dot(self.normal, vi)) / denom
                        mid = _lerp(vi, vj, t)
                        f.append(mid)
                        b.append(mid)
            if len(f) >= 3:
                front.append(Polygon(f))
            if len(b) >= 3:
                back.append(Polygon(b))


class Polygon:
    __slots__ = ("vertices", "plane")

    def __init__(self, vertices: list[Vec3]):
        self.vertices = vertices
        self.plane = Plane.from_points(vertices[0], vertices[1], vertices[2])

    def flip(self) -> None:
        self.vertices = list(reversed(self.vertices))
        if self.plane:
            self.plane.flip()

    def valid(self) -> bool:
        return self.plane is not None


class Node:
    __slots__ = ("plane", "front", "back", "polygons")

    def __init__(self, polygons: list[Polygon] | None = None):
        self.plane: Plane | None = None
        self.front: "Node | None" = None
        self.back: "Node | None" = None
        self.polygons: list[Polygon] = []
        if polygons:
            self.build(polygons)

    def invert(self) -> None:
        for p in self.polygons:
            p.flip()
        if self.plane:
            self.plane.flip()
        if self.front:
            self.front.invert()
        if self.back:
            self.back.invert()
        self.front, self.back = self.back, self.front

    def clip_polygons(self, polygons: list[Polygon]) -> list[Polygon]:
        if not self.plane:
            return list(polygons)
        front: list[Polygon] = []
        back: list[Polygon] = []
        for poly in polygons:
            self.plane.split_polygon(poly, front, back, front, back)
        if self.front:
            front = self.front.clip_polygons(front)
        back = self.back.clip_polygons(back) if self.back else []
        return front + back

    def clip_to(self, bsp: "Node") -> None:
        self.polygons = bsp.clip_polygons(self.polygons)
        if self.front:
            self.front.clip_to(bsp)
        if self.back:
            self.back.clip_to(bsp)

    def all_polygons(self) -> list[Polygon]:
        out = list(self.polygons)
        if self.front:
            out += self.front.all_polygons()
        if self.back:
            out += self.back.all_polygons()
        return out

    def build(self, polygons: list[Polygon]) -> None:
        polygons = [p for p in polygons if p.valid()]
        if not polygons:
            return
        if not self.plane:
            self.plane = Plane(polygons[0].plane.normal, polygons[0].plane.w)
        front: list[Polygon] = []
        back: list[Polygon] = []
        for poly in polygons:
            self.plane.split_polygon(poly, self.polygons, self.polygons, front, back)
        if front:
            if not self.front:
                self.front = Node()
            self.front.build(front)
        if back:
            if not self.back:
                self.back = Node()
            self.back.build(back)


# ------------------------------------------------------------ mesh <-> polygons
def _mesh_to_polygons(mesh: Mesh) -> list[Polygon]:
    polys = []
    for a, b, c in mesh.triangles:
        p = Polygon([mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]])
        if p.valid():
            polys.append(p)
    return polys


def _polygons_to_mesh(polygons: list[Polygon]) -> Mesh:
    verts: list[Vec3] = []
    tris = []
    for poly in polygons:
        vs = poly.vertices
        base = len(verts)
        verts.extend(vs)
        for i in range(1, len(vs) - 1):     # fan triangulation
            tris.append((base, base + i, base + i + 1))
    return Mesh(verts, tris)


# --------------------------------------------------------------------- ops
def union(a: Mesh, b: Mesh) -> Mesh:
    if a.is_empty():
        return Mesh(list(b.vertices), list(b.triangles))
    if b.is_empty():
        return Mesh(list(a.vertices), list(a.triangles))
    na, nb = Node(_mesh_to_polygons(a)), Node(_mesh_to_polygons(b))
    na.clip_to(nb)
    nb.clip_to(na)
    nb.invert()
    nb.clip_to(na)
    nb.invert()
    na.build(nb.all_polygons())
    return _polygons_to_mesh(na.all_polygons())


def difference(a: Mesh, b: Mesh) -> Mesh:
    if a.is_empty() or b.is_empty():
        return Mesh(list(a.vertices), list(a.triangles))
    na, nb = Node(_mesh_to_polygons(a)), Node(_mesh_to_polygons(b))
    na.invert()
    na.clip_to(nb)
    nb.clip_to(na)
    nb.invert()
    nb.clip_to(na)
    nb.invert()
    na.build(nb.all_polygons())
    na.invert()
    return _polygons_to_mesh(na.all_polygons())


def intersection(a: Mesh, b: Mesh) -> Mesh:
    if a.is_empty() or b.is_empty():
        return Mesh()
    na, nb = Node(_mesh_to_polygons(a)), Node(_mesh_to_polygons(b))
    na.invert()
    nb.clip_to(na)
    nb.invert()
    na.clip_to(nb)
    nb.clip_to(na)
    na.build(nb.all_polygons())
    na.invert()
    return _polygons_to_mesh(na.all_polygons())
