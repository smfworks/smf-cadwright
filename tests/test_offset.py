import pytest

from cadwright.scad import render_scad, ScadError


def test_offset_grows_outward():
    m = render_scad("linear_extrude(height=2) offset(r=2) square([10,10]);")
    mn, mx = m.bbox()
    assert round(mx[0] - mn[0]) == 14 and round(mn[0]) == -2


def test_offset_shrinks_inward():
    m = render_scad("linear_extrude(height=2) offset(delta=-3) circle(r=10,$fn=64);")
    mn, mx = m.bbox()
    assert round(mx[0] - mn[0]) == 14          # 20 - 2*3


def test_offset_shell_ring():
    # outer = grown profile, minus the original -> a wall/shell ring
    m = render_scad("""
        linear_extrude(height=3) difference() {
            offset(r=2) square([30,20], center=true);
            square([30,20], center=true);
        }
    """)
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert round(mx[0] - mn[0]) == 34          # 30 + 2*2


def test_offset_of_boolean_errors():
    with pytest.raises(ScadError):
        render_scad("linear_extrude(height=2) offset(r=1) "
                    "difference(){ circle(5,$fn=32); circle(2,$fn=32); }")


def test_offset_zero_is_identity():
    a = render_scad("linear_extrude(height=2) circle(r=5,$fn=48);")
    b = render_scad("linear_extrude(height=2) offset(r=0) circle(r=5,$fn=48);")
    assert len(a.triangles) == len(b.triangles)
