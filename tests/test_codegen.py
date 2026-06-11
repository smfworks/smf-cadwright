from cadwright import codegen


def test_tube_template():
    scad = codegen.generate("a tube outer 20mm inner 10mm 8mm tall", mode="mock")
    assert "difference()" in scad
    assert "outer_d" in scad and "inner_d" in scad


def test_plate_with_threaded_holes():
    scad = codegen.generate("a 50mm wide 30mm deep plate 4mm thick with M4 holes",
                            mode="mock")
    assert "width = 50" in scad
    assert "hole_d = 4.3" in scad           # M4 clearance


def test_cylinder_template():
    scad = codegen.generate("a 24mm diameter knob 10mm tall", mode="mock")
    assert "diameter = 24" in scad and "height = 10" in scad


def test_edit_changes_a_variable():
    scad = codegen.generate("a 24mm diameter knob 10mm tall", mode="mock")
    new, note = codegen.edit(scad, "make it 18mm tall", mode="mock")
    assert "height = 18" in new
    assert "height" in note


def test_edit_without_number_is_noop():
    scad = codegen.generate("a tube", mode="mock")
    new, note = codegen.edit(scad, "make it nicer", mode="mock")
    assert new == scad and "nothing changed" in note
