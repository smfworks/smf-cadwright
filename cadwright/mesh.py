"""Mesh container, 4x4 transforms, and exporters (STL + 3MF).

A Mesh is a plain triangle soup: a list of (x, y, z) vertices and a list of
(i, j, k) triangles indexing into them. Everything downstream — primitives,
CSG, the evaluator — produces and consumes Mesh objects. Units are millimetres
(3MF declares mm), which is what 3D-printer slicers expect.

No third-party dependencies: STL and 3MF are written with the standard library.
"""
from __future__ import annotations

import math
import struct
import zipfile
from dataclasses import dataclass, field

Vec3 = tuple[float, float, float]
Tri = tuple[int, int, int]
Mat4 = tuple[tuple[float, float, float, float], ...]


def identity() -> Mat4:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def mat_mul(a: Mat4, b: Mat4) -> Mat4:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
        for i in range(4)
    )


def translate_m(x: float, y: float, z: float) -> Mat4:
    return (
        (1.0, 0.0, 0.0, float(x)),
        (0.0, 1.0, 0.0, float(y)),
        (0.0, 0.0, 1.0, float(z)),
        (0.0, 0.0, 0.0, 1.0),
    )


def scale_m(x: float, y: float, z: float) -> Mat4:
    return (
        (float(x), 0.0, 0.0, 0.0),
        (0.0, float(y), 0.0, 0.0),
        (0.0, 0.0, float(z), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _rot_axis(angle_deg: float, axis: Vec3) -> Mat4:
    ax, ay, az = axis
    length = math.sqrt(ax * ax + ay * ay + az * az)
    if length == 0:
        return identity()
    ax, ay, az = ax / length, ay / length, az / length
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    t = 1 - c
    return (
        (t * ax * ax + c, t * ax * ay - s * az, t * ax * az + s * ay, 0.0),
        (t * ax * ay + s * az, t * ay * ay + c, t * ay * az - s * ax, 0.0),
        (t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def rotate_xyz(rx: float, ry: float, rz: float) -> Mat4:
    """OpenSCAD rotate([x,y,z]) = rotate z, then y, then x (applied X*Y*Z)."""
    m = _rot_axis(rz, (0, 0, 1))
    m = mat_mul(_rot_axis(ry, (0, 1, 0)), m)
    m = mat_mul(_rot_axis(rx, (1, 0, 0)), m)
    return m


def mirror_m(nx: float, ny: float, nz: float) -> Mat4:
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return identity()
    nx, ny, nz = nx / length, ny / length, nz / length
    return (
        (1 - 2 * nx * nx, -2 * nx * ny, -2 * nx * nz, 0.0),
        (-2 * nx * ny, 1 - 2 * ny * ny, -2 * ny * nz, 0.0),
        (-2 * nx * nz, -2 * ny * nz, 1 - 2 * nz * nz, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def apply(m: Mat4, v: Vec3) -> Vec3:
    x, y, z = v
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def _determinant3(m: Mat4) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


@dataclass
class Mesh:
    vertices: list[Vec3] = field(default_factory=list)
    triangles: list[Tri] = field(default_factory=list)

    # ----------------------------------------------------------- construction
    @staticmethod
    def concat(meshes: list["Mesh"]) -> "Mesh":
        out = Mesh()
        for m in meshes:
            out.append(m)
        return out

    def append(self, other: "Mesh") -> None:
        base = len(self.vertices)
        self.vertices.extend(other.vertices)
        self.triangles.extend((a + base, b + base, c + base) for a, b, c in other.triangles)

    def transformed(self, m: Mat4) -> "Mesh":
        verts = [apply(m, v) for v in self.vertices]
        tris = self.triangles
        # A negative-determinant transform (e.g. mirror) flips winding; fix it so
        # outward normals stay outward.
        if _determinant3(m) < 0:
            tris = [(a, c, b) for a, b, c in self.triangles]
        return Mesh(verts, list(tris))

    # ---------------------------------------------------------------- queries
    def bbox(self) -> tuple[Vec3, Vec3]:
        if not self.vertices:
            return ((0, 0, 0), (0, 0, 0))
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def is_empty(self) -> bool:
        return not self.triangles

    # -------------------------------------------------------------- exporters
    def to_stl_bytes(self, name: str = "cadwright") -> bytes:
        # Binary STL.
        out = bytearray(b"\0" * 80)
        out += struct.pack("<I", len(self.triangles))
        for a, b, c in self.triangles:
            va, vb, vc = self.vertices[a], self.vertices[b], self.vertices[c]
            n = _normal(va, vb, vc)
            out += struct.pack("<3f", *n)
            for v in (va, vb, vc):
                out += struct.pack("<3f", *v)
            out += struct.pack("<H", 0)
        return bytes(out)

    def to_3mf_model_xml(self) -> str:
        verts = "".join(
            f'<vertex x="{v[0]:.6g}" y="{v[1]:.6g}" z="{v[2]:.6g}"/>'
            for v in self.vertices
        )
        tris = "".join(
            f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in self.triangles
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
            "<resources>"
            '<object id="1" type="model"><mesh>'
            f"<vertices>{verts}</vertices>"
            f"<triangles>{tris}</triangles>"
            "</mesh></object>"
            "</resources>"
            '<build><item objectid="1"/></build>'
            "</model>"
        )

    def write_3mf(self, path: str) -> str:
        content_types = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
            "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            "</Relationships>"
        )
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", rels)
            z.writestr("3D/3dmodel.model", self.to_3mf_model_xml())
        return path


def _normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / length, ny / length, nz / length)
