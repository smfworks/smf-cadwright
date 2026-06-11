import pytest

from cadwright import codegen, csg
from cadwright.csg import Polygon, Node
from cadwright.mesh import Mesh
from cadwright.primitives import sphere, cube
from cadwright.scad import render_scad, ScadError


def _normal_len(va, vb, vc):
    ux, uy, uz = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
    vx, vy, vz = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
    nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    return (nx * nx + ny * ny + nz * nz) ** 0.5


def test_export_rejects_out_of_range_indices(tmp_path):
    bad = Mesh([(0, 0, 0), (1, 0, 0)], [(0, 1, 2)])   # index 2 doesn't exist
    with pytest.raises(ValueError):
        bad.to_3mf_model_xml()
    with pytest.raises(ValueError):
        bad.to_stl_bytes()


def test_polyhedron_validates_indices():
    with pytest.raises(ValueError):
        render_scad("polyhedron(points=[[0,0,0],[1,0,0],[0,1,0]], faces=[[0,1,3]]);")


def test_csg_survives_degenerate_polygon():
    # A collinear "triangle" has plane=None; splitting must not crash.
    degenerate = Polygon([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    assert degenerate.plane is None
    node = Node(csg._mesh_to_polygons(cube(10)))
    # Clipping a degenerate polygon against a real BSP should simply drop it.
    out = node.clip_polygons([degenerate])
    assert isinstance(out, list)


def test_sphere_has_no_degenerate_triangles():
    m = sphere(10, fn=8)
    bad = sum(1 for a, b, c in m.triangles
              if _normal_len(m.vertices[a], m.vertices[b], m.vertices[c]) < 1e-9)
    assert bad == 0


def test_sphere_difference_is_clean():
    out = csg.difference(cube([20, 20, 20], center=True), sphere(8, fn=16))
    assert not out.is_empty()


def test_m25_thread_hole():
    scad = codegen.generate("a plate with M2.5 holes", mode="mock")
    assert "hole_d = 2.9" in scad        # not the M2 value 2.4
