import zipfile

from cadwright import CADwright


def test_generate_render_export(tmp_path):
    cad = CADwright()
    cad.generate("a tube outer 20mm inner 10mm 8mm tall")
    stats = cad.stats()
    assert stats["triangles"] > 0 and not stats["empty"]
    path = str(tmp_path / "tube.3mf")
    cad.export_3mf(path)
    with zipfile.ZipFile(path) as z:
        assert "3D/3dmodel.model" in z.namelist()


def test_edit_rebuilds_mesh(tmp_path):
    cad = CADwright()
    cad.generate("a 24mm diameter knob 10mm tall")
    before = cad.stats()["size_mm"][2]      # height
    cad.edit("make it 30mm tall")
    after = cad.stats()["size_mm"][2]
    assert round(before) == 10 and round(after) == 30


def test_preview_svg_is_svg():
    cad = CADwright()
    cad.generate("a 20mm cube")
    svg = cad.preview_svg()
    assert svg.lstrip().startswith("<svg") and "polygon" in svg


def test_stl_export(tmp_path):
    cad = CADwright()
    cad.generate("a tube outer 16 inner 8 6 tall")
    path = str(tmp_path / "m.stl")
    cad.export_stl(path)
    with open(path, "rb") as f:
        head = f.read(84)
    assert len(head) == 84
