import pytest

from cadwright.scad import render_scad, ScadError
from cadwright.shapes2d import text as text2d


def test_rotate_extrude_ring_spans_axis():
    m = render_scad("rotate_extrude($fn=48) translate([10,0]) square([4,10]);")
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert round(mn[0]) == -14 and round(mx[0]) == 14    # radius 10..14 revolved
    assert round(mx[2] - mn[2]) == 10


def test_rotate_extrude_vase_exports(tmp_path):
    m = render_scad("rotate_extrude($fn=32) "
                    "polygon(points=[[2,0],[12,0],[8,20],[10,40],[3,40]]);")
    assert not m.is_empty()
    m.write_3mf(str(tmp_path / "vase.3mf"))      # _check validates indices


def test_text_extrudes_to_size_height():
    m = render_scad('linear_extrude(height=2) text("HI", size=10);')
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert round(mx[1] - mn[1]) == 10            # glyph height == size
    assert round(mx[2] - mn[2]) == 2


def test_text_width_scales_with_length():
    one = render_scad('linear_extrude(height=1) text("I", size=10);')
    three = render_scad('linear_extrude(height=1) text("III", size=10);')
    assert three.bbox()[1][0] > one.bbox()[1][0]   # wider for more chars


def test_unknown_glyph_is_space_no_crash():
    outlines = text2d("~", size=10)              # not in font -> space -> no squares
    assert outlines == []


def test_minkowski_still_unsupported():
    with pytest.raises(ScadError):
        render_scad("minkowski(){ cube(10); sphere(2); }")
