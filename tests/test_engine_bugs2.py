from cadwright.scad import render_scad
from cadwright.hull import convex_hull


def _area2(a, b, c):
    ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    return nx * nx + ny * ny + nz * nz


def test_revolve_axis_profile_has_no_degenerate_triangles():
    # profile touches the axis (x=0) at two points -> used to make zero-area tris
    m = render_scad("rotate_extrude($fn=24) "
                    "polygon(points=[[0,0],[5,0],[5,10],[0,10]]);")
    assert not m.is_empty()
    assert all(_area2(m.vertices[a], m.vertices[b], m.vertices[c]) > 1e-12
               for a, b, c in m.triangles)


def test_hull_of_cube_corners_is_12_triangles():
    corners = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
               (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10),
               (10, 0, 0), (0, 0, 0)]   # duplicates included on purpose
    m = convex_hull(corners)
    assert len(m.triangles) == 12       # 6 quad faces -> 12 tris


def test_nested_difference_two_holes_valid(tmp_path):
    two = render_scad("""
        linear_extrude(height=5) difference() {
            difference() {
                square([40,40], center=true);
                translate([-10,-10]) circle(r=4, $fn=32);
            }
            translate([10,10]) circle(r=4, $fn=32);
        }
    """)
    one = render_scad("""
        linear_extrude(height=5) difference() {
            square([40,40], center=true);
            translate([-10,-10]) circle(r=4, $fn=32);
        }
    """)
    assert not two.is_empty()
    two.write_3mf(str(tmp_path / "two.3mf"))     # _check validates indices
    assert len(two.triangles) > len(one.triangles)   # the 2nd hole added geometry
