"""CADwright — an OpenClaw add-on that turns a description (or image) into a
3D-printable model: AI codegen -> our own OpenSCAD-subset engine -> 3MF, all in
one place. No external OpenSCAD install, no GPL — a clean-room engine.
"""
from .pipeline import CADwright, Project
from .scad import render_scad, ScadError
from .mesh import Mesh
from . import primitives, csg, codegen, preview

__all__ = [
    "CADwright", "Project", "render_scad", "ScadError", "Mesh",
    "primitives", "csg", "codegen", "preview",
]
__version__ = "0.1.0"
