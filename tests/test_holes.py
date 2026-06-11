from cadwright.scad import render_scad


def test_washer_is_hollow():
    washer = render_scad("linear_extrude(height=3) "
                         "difference(){ circle(r=10,$fn=64); circle(r=4,$fn=64); }")
    solid = render_scad("linear_extrude(height=3) circle(r=10,$fn=64);")
    assert not washer.is_empty()
    assert len(washer.triangles) > len(solid.triangles)   # hole added geometry
    mn, mx = washer.bbox()
    assert round(mx[0] - mn[0]) == 20 and round(mx[2] - mn[2]) == 3


def test_window_frame():
    frame = render_scad("linear_extrude(height=2) "
                        "difference(){ square([40,30],center=true); "
                        "square([30,20],center=true); }")
    assert not frame.is_empty()


def test_offset_hole_via_translate():
    m = render_scad("linear_extrude(height=4) "
                    "difference(){ square([20,20]); "
                    "translate([5,5]) circle(r=3,$fn=32); }")
    assert not m.is_empty()


def test_2d_intersection_in_extrude():
    m = render_scad("linear_extrude(height=2) "
                    "intersection(){ square([20,20]); "
                    "translate([10,10]) circle(r=12,$fn=48); }")
    assert not m.is_empty()
    mn, mx = m.bbox()
    assert mx[0] - mn[0] <= 20.001            # clipped to the square


def test_washer_exports_valid_3mf(tmp_path):
    m = render_scad("linear_extrude(height=3) "
                    "difference(){ circle(r=8,$fn=48); circle(r=3,$fn=48); }")
    m.write_3mf(str(tmp_path / "washer.3mf"))   # _check validates indices


def test_plain_extrude_unaffected():
    m = render_scad("linear_extrude(height=10) circle(r=5,$fn=48);")
    mn, mx = m.bbox()
    assert (round(mx[0] - mn[0]), round(mx[2] - mn[2])) == (10, 10)
