import math

import pytest

from cadwright.scad import render_scad, ScadError


def test_parametric_bracket_dimensions():
    src = """
    width = 40; depth = 30; thick = 4; hole_r = 2.5; $fn = 32;
    module plate(w,d,t){ cube([w,d,t]); }
    difference(){
      plate(width, depth, thick);
      translate([10, depth/2, -1]) cylinder(h=thick+2, r=hole_r);
    }
    """
    m = render_scad(src)
    assert not m.is_empty()
    (mnx, mny, mnz), (mxx, mxy, mxz) = m.bbox()
    assert round(mxx - mnx) == 40 and round(mxy - mny) == 30 and round(mxz - mnz) == 4


def test_for_loop_repeats_geometry():
    one = render_scad("cube(2);")
    many = render_scad("for (x=[0:10:30]) translate([x,0,0]) cube(2);")
    # 4 separated cubes -> more triangles than a single cube
    assert len(many.triangles) > len(one.triangles) * 3


def test_if_else_selects_branch():
    a = render_scad("flag=1; if (flag) cube(10); else sphere(5);")
    (mn, mx) = a.bbox()
    assert round(mx[0] - mn[0]) == 10        # took the cube branch


def test_expressions_and_trig_degrees():
    # cos(60)=0.5 -> cube side 5
    m = render_scad("s = 10 * cos(60); cube(s);")
    (mn, mx) = m.bbox()
    assert abs((mx[0] - mn[0]) - 5.0) < 1e-6


def test_unsupported_feature_errors():
    with pytest.raises(ScadError):
        render_scad("minkowski(){ cube(10); sphere(2); }")


def test_undefined_variable_errors():
    with pytest.raises(ScadError):
        render_scad("cube(missing);")
