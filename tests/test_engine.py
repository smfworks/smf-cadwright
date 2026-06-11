import zipfile

from cadwright import csg
from cadwright.primitives import cube, cylinder, sphere, polyhedron


def test_cube_has_12_triangles():
    assert len(cube(10).triangles) == 12


def test_difference_makes_a_hole():
    box = cube([20, 20, 10], center=True)
    hole = cylinder(h=40, r=5, center=True, fn=32)
    out = csg.difference(box, hole)
    assert not out.is_empty()
    assert len(out.triangles) > len(box.triangles)   # hole added geometry


def test_union_of_identical_cubes_is_a_cube():
    out = csg.union(cube(10), cube(10))
    # coincident solids collapse — far fewer than 24 triangles
    assert 0 < len(out.triangles) <= 16


def test_intersection_nonempty_and_bounded():
    out = csg.intersection(cube(10, center=True), sphere(6, fn=24))
    assert not out.is_empty()
    (mnx, mny, mnz), (mxx, mxy, mxz) = out.bbox()
    assert mxx - mnx <= 10.001 and mxx - mnx >= 9.0   # clipped to the cube


def test_3mf_is_valid_zip(tmp_path):
    box = cube([10, 10, 10])
    path = str(tmp_path / "box.3mf")
    box.write_3mf(path)
    with zipfile.ZipFile(path) as z:
        assert "3D/3dmodel.model" in z.namelist()
        assert "[Content_Types].xml" in z.namelist()
        xml = z.read("3D/3dmodel.model").decode()
        assert "<vertex" in xml and "<triangle" in xml
        assert 'unit="millimeter"' in xml


def test_stl_binary_header():
    data = cube(5).to_stl_bytes()
    # 80-byte header + 4-byte count + 50 bytes per triangle
    assert len(data) == 84 + 50 * 12


def test_polyhedron_tetra():
    m = polyhedron([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]],
                   [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]])
    assert len(m.triangles) == 4
