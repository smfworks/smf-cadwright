"""CADwright CLI.

    cadwright gen "<description>" [--image ref.png] [--out model.3mf]
                                 [--stl model.stl] [--preview model.svg] [--scad model.scad]
    cadwright render model.scad [--out model.3mf] [--preview model.svg]
    cadwright shell              # interactive: generate -> edit -> export loop

Offline by default (deterministic mock codegen). Set CADWRIGHT_LLM=real +
CADWRIGHT_API_BASE/_MODEL/_API_KEY to drive a real model.
"""
from __future__ import annotations

import argparse
import sys

from .pipeline import CADwright
from .scad import ScadError


def _emit(cad: CADwright, args) -> None:
    print(cad.project.scad)
    print("stats:", cad.stats())
    if getattr(args, "scad", None):
        with open(args.scad, "w", encoding="utf-8") as f:
            f.write(cad.project.scad)
        print("wrote", args.scad)
    if getattr(args, "out", None):
        print("wrote", cad.export_3mf(args.out))
    if getattr(args, "stl", None):
        print("wrote", cad.export_stl(args.stl))
    if getattr(args, "preview", None):
        cad.preview_svg(args.preview)
        print("wrote", args.preview)


def cmd_gen(args) -> int:
    cad = CADwright()
    try:
        cad.generate(args.prompt, image_path=args.image)
    except ScadError as e:
        print(f"engine error: {e}", file=sys.stderr)
        return 1
    _emit(cad, args)
    return 0


def cmd_render(args) -> int:
    cad = CADwright()
    with open(args.file, "r", encoding="utf-8") as f:
        scad = f.read()
    try:
        cad.set_scad(scad)
    except ScadError as e:
        print(f"engine error: {e}", file=sys.stderr)
        return 1
    print("stats:", cad.stats())
    if args.out:
        print("wrote", cad.export_3mf(args.out))
    if args.preview:
        cad.preview_svg(args.preview)
        print("wrote", args.preview)
    return 0


def cmd_shell(_args) -> int:
    cad = CADwright()
    print("CADwright shell — describe a part, then refine it.")
    print("commands: <description> | edit <change> | scad | stats | "
          "export <file.3mf|.stl|.svg> | new | quit\n")
    while True:
        try:
            line = input("cadwright> ").strip()
        except EOFError:
            break
        if not line:
            continue
        low = line.lower()
        if low in ("quit", "exit", "q"):
            break
        try:
            if low == "scad":
                print(cad.project.scad or "(nothing yet)")
            elif low == "stats":
                print(cad.stats() if cad.project.scad else "(nothing yet)")
            elif low == "new":
                cad = CADwright()
                print("cleared.")
            elif low.startswith("edit "):
                print("  ", cad.edit(line[5:].strip()))
                print("  stats:", cad.stats())
            elif low.startswith("export "):
                path = line[7:].strip()
                if path.endswith(".stl"):
                    print("  wrote", cad.export_stl(path))
                elif path.endswith(".svg"):
                    cad.preview_svg(path)
                    print("  wrote", path)
                else:
                    print("  wrote", cad.export_3mf(path))
            else:
                cad.generate(line)
                print("  stats:", cad.stats())
        except ScadError as e:
            print(f"  engine error: {e}")
        except Exception as e:  # keep the shell alive
            print(f"  error: {e}")
    print("bye.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cadwright", description="CADwright — AI -> SCAD -> 3MF")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen", help="generate a model from a description")
    g.add_argument("prompt")
    g.add_argument("--image", default=None, help="reference image (real/vision providers)")
    g.add_argument("--out", default=None, help="export 3MF path")
    g.add_argument("--stl", default=None, help="export STL path")
    g.add_argument("--preview", default=None, help="write SVG preview path")
    g.add_argument("--scad", default=None, help="write the generated .scad path")
    g.set_defaults(func=cmd_gen)

    r = sub.add_parser("render", help="render an existing .scad file")
    r.add_argument("file")
    r.add_argument("--out", default=None, help="export 3MF path")
    r.add_argument("--preview", default=None, help="write SVG preview path")
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("shell", help="interactive generate -> edit -> export loop")
    s.set_defaults(func=cmd_shell)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
