"""CADwright demo — offline (mock codegen). Generates a few parts, edits one,
and exports 3MF + SVG previews.

    python demo.py
"""
from __future__ import annotations

import os

from cadwright import CADwright

OUT = os.path.join(os.path.dirname(__file__), "out")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    cad = CADwright()

    print("=" * 64)
    print("1) Tube / standoff")
    print("=" * 64)
    cad.generate("an M3 standoff tube, outer 8mm, inner 3.2mm, 12mm tall")
    print(cad.project.scad)
    print("stats:", cad.stats())
    print("3MF ->", cad.export_3mf(os.path.join(OUT, "standoff.3mf")))
    print("SVG ->", cad.preview_svg(os.path.join(OUT, "standoff.svg")) and
          os.path.join(OUT, "standoff.svg"))

    print("\n" + "=" * 64)
    print("2) Mounting plate with holes — then edit it")
    print("=" * 64)
    cad.generate("a 50mm wide 30mm deep mounting plate, 4mm thick, with M4 holes")
    print(cad.project.scad)
    print("stats:", cad.stats())
    print("edit ->", cad.edit("make it 6 mm thick"))
    print("after edit stats:", cad.stats())
    cad.export_3mf(os.path.join(OUT, "plate.3mf"))
    cad.preview_svg(os.path.join(OUT, "plate.svg"))
    print("exported plate.3mf + plate.svg")

    print("\n" + "=" * 64)
    print("3) Knurl-less knob (cylinder) -> taller")
    print("=" * 64)
    cad.generate("a 24mm diameter knob, 10mm tall")
    print("stats:", cad.stats())
    print("edit ->", cad.edit("make it 18mm tall"))
    print("after edit stats:", cad.stats())

    print("\nall outputs in:", OUT)


if __name__ == "__main__":
    main()
