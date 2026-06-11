"""CADwright pipeline: prompt/image -> SCAD -> mesh -> preview + 3MF, with an
iterative plain-English edit loop. This is the one-place workflow that replaces
"web AI -> copy code -> OpenSCAD -> render -> export"."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import codegen
from .mesh import Mesh
from .preview import to_svg, write_svg
from .scad import render_scad


@dataclass
class Project:
    prompt: str = ""
    scad: str = ""
    mesh: Mesh = field(default_factory=Mesh)
    history: list[str] = field(default_factory=list)


class CADwright:
    """Stateful session holding the current model."""

    def __init__(self) -> None:
        self.project = Project()

    # --------------------------------------------------------------- build
    def generate(self, prompt: str, image_path: str | None = None) -> Project:
        scad = codegen.generate(prompt, image_path)
        mesh = render_scad(scad)
        self.project = Project(prompt=prompt, scad=scad, mesh=mesh,
                               history=[f"generate: {prompt}"])
        return self.project

    def set_scad(self, scad: str) -> Project:
        self.project.scad = scad
        self.project.mesh = render_scad(scad)
        self.project.history.append("load scad")
        return self.project

    def edit(self, instruction: str) -> str:
        new_scad, note = codegen.edit(self.project.scad, instruction)
        self.project.mesh = render_scad(new_scad)
        self.project.scad = new_scad
        self.project.history.append(f"edit: {instruction} -> {note}")
        return note

    # --------------------------------------------------------------- output
    def stats(self) -> dict:
        (mnx, mny, mnz), (mxx, mxy, mxz) = self.project.mesh.bbox()
        return {
            "triangles": len(self.project.mesh.triangles),
            "vertices": len(self.project.mesh.vertices),
            "size_mm": (round(mxx - mnx, 3), round(mxy - mny, 3), round(mxz - mnz, 3)),
            "empty": self.project.mesh.is_empty(),
        }

    def preview_svg(self, path: str | None = None) -> str:
        svg = to_svg(self.project.mesh)
        if path:
            write_svg(self.project.mesh, path)
        return svg

    def export_3mf(self, path: str) -> str:
        return self.project.mesh.write_3mf(path)

    def export_stl(self, path: str) -> str:
        with open(path, "wb") as f:
            f.write(self.project.mesh.to_stl_bytes())
        return path
