import pytest

from cadwright.scad import render_scad, ScadError
from cadwright.hull import convex_hull
from cadwright.primitives import cube


def test_hull_of_two_spheres_spans_both():
    m = render_scad("$fn=16; hull(){ sphere(5); translate([20,0,0]) sphere(5); }")
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert round(mn[0]) == -5 and round(mx[0]) == 25      # capsule spans both


def test_hull_coplanar_points_is_empty():
    # all points in z=0 plane -> no volume -> empty hull
    pts = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (10, 10, 0)]
    assert convex_hull(pts).is_empty()


def test_hull_exports_valid_3mf(tmp_path):
    m = render_scad("hull(){ cube(5); translate([10,10,10]) cube(5); }")
    path = str(tmp_path / "h.3mf")
    m.write_3mf(path)                  # _check would raise on bad indices
    assert not m.is_empty()


def test_extrude_circle_is_cylinder_like():
    m = render_scad("linear_extrude(height=10) circle(r=5, $fn=48);")
    mn, mx = m.bbox()
    assert round(mx[0] - mn[0]) == 10 and round(mx[2] - mn[2]) == 10


def test_extrude_square_centered():
    m = render_scad("linear_extrude(height=5, center=true) square([10,20], center=true);")
    mn, mx = m.bbox()
    assert (round(mx[0] - mn[0]), round(mx[1] - mn[1]), round(mx[2] - mn[2])) == (10, 20, 5)
    assert round(mn[2], 1) == -2.5


def test_extrude_polygon_prism():
    m = render_scad("linear_extrude(height=4) polygon(points=[[0,0],[10,0],[5,8]]);")
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert round(mx[2] - mn[2]) == 4


def test_twist_adds_geometry():
    plain = render_scad("linear_extrude(height=20) square([10,4], center=true);")
    twisted = render_scad("linear_extrude(height=20, twist=90, slices=12) square([10,4], center=true);")
    assert len(twisted.triangles) > len(plain.triangles)


def test_2d_primitive_outside_extrude_errors():
    with pytest.raises(ScadError):
        render_scad("circle(5);")


def test_extrude_then_difference():
    m = render_scad("""
        difference() {
            linear_extrude(height=10) circle(r=10, $fn=48);
            translate([0,0,-1]) cylinder(h=12, r=4, $fn=48);
        }
    """)
    assert not m.is_empty()
