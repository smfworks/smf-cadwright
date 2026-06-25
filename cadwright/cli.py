"""CADwright CLI.

    cadwright gen "<description>" [--image ref.png] [--out model.3mf]
                                 [--stl model.stl] [--preview model.svg] [--scad model.scad]
                                 [--print]
    cadwright render model.scad [--out model.3mf] [--preview model.svg]
    cadwright printer status           # show printer status
    cadwright printer upload <file.3mf> [--print]
    cadwright printer home             # home axes (G28)
    cadwright printer stop              # stop current print
    cadwright shell              # interactive: generate -> edit -> export loop

Offline by default (deterministic mock codegen). Set CADWRIGHT_LLM=real +
CADWRIGHT_API_BASE/_MODEL/_API_KEY to drive a real model.

For --print / printer commands, set:
  BAMBU_HOST=<printer IP>
  BAMBU_ACCESS_CODE=<8-digit LAN access code from printer LCD>
"""
from __future__ import annotations

import argparse
import os
import sys

from .pipeline import CADwright
from .scad import ScadError

BAMBU_HOST = os.environ.get("BAMBU_HOST", "")
BAMBU_CODE = os.environ.get("BAMBU_ACCESS_CODE", "")


def _get_printer(args):
    from .bambu import BambuPrinter, BambuError
    host = getattr(args, "host", None) or BAMBU_HOST
    code = getattr(args, "access_code", None) or BAMBU_CODE
    if not host or not code:
        print("Error: set BAMBU_HOST and BAMBU_ACCESS_CODE env vars, or use --host/--access-code", file=sys.stderr)
        sys.exit(2)
    return BambuPrinter(host=host, access_code=code)


def _send_to_printer(file_path: str) -> None:
    """Upload a 3MF to the Bambu printer and start printing."""
    from .bambu import BambuPrinter, BambuError
    if not BAMBU_HOST or not BAMBU_CODE:
        print("Error: --print requires BAMBU_HOST and BAMBU_ACCESS_CODE env vars", file=sys.stderr)
        return
    try:
        printer = BambuPrinter(host=BAMBU_HOST, access_code=BAMBU_CODE)
        print(f"Uploading {file_path} to printer at {BAMBU_HOST}...")
        remote = printer.upload_3mf(file_path)
        print(f"  uploaded to {remote}")
        print("Starting print...")
        resp = printer.start_print(remote)
        result = resp.get("print", {}).get("result", "unknown")
        print(f"  print result: {result}")
    except BambuError as e:
        print(f"  printer error: {e}", file=sys.stderr)


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
    if getattr(args, "print", False) and getattr(args, "out", None):
        _send_to_printer(args.out)


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
    pending_image = None
    print("CADwright shell — describe a part, then refine it.")
    print("commands: <description> | image <path> | edit <change> | scad | stats | "
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
                pending_image = None
                print("cleared.")
            elif low.startswith("image "):
                pending_image = line[6:].strip().strip('"')
                print(f"  reference image set for next description: {pending_image}")
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
                cad.generate(line, image_path=pending_image)
                if pending_image:
                    pending_image = None        # consumed
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
    g.add_argument("--print", action="store_true", help="upload to Bambu printer and start printing")
    g.set_defaults(func=cmd_gen)

    r = sub.add_parser("render", help="render an existing .scad file")
    r.add_argument("file")
    r.add_argument("--out", default=None, help="export 3MF path")
    r.add_argument("--preview", default=None, help="write SVG preview path")
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("shell", help="interactive generate -> edit -> export loop")
    s.set_defaults(func=cmd_shell)

       # printer subcommand
    p = sub.add_parser("printer", help="Bambu Lab printer control")
    p.add_argument("--host", default=None, help="printer IP (or set BAMBU_HOST)")
    p.add_argument("--access-code", default=None, help="LAN access code (or set BAMBU_ACCESS_CODE)")
    ps = p.add_subparsers(dest="printer_cmd", required=True)

    ps_status = ps.add_parser("status", help="show printer status")
    ps_status.set_defaults(func=cmd_printer_status)

    ps_upload = ps.add_parser("upload", help="upload a 3MF file to the printer")
    ps_upload.add_argument("file")
    ps_upload.add_argument("--print", action="store_true", help="start printing after upload")
    ps_upload.set_defaults(func=cmd_printer_upload)

    ps_home = ps.add_parser("home", help="home all axes (G28)")
    ps_home.set_defaults(func=cmd_printer_home)

    ps_stop = ps.add_parser("stop", help="stop current print")
    ps_stop.set_defaults(func=cmd_printer_stop)
    return parser


def cmd_printer_status(args) -> int:
    from .bambu import BambuError
    try:
        printer = _get_printer(args)
        status = printer.get_status()
        state = status.get("gcode_state", "UNKNOWN")
        pct = status.get("mc_percent", 0)
        remaining = status.get("mc_remaining_time", 0)
        nozzle = status.get("nozzle_temper", 0)
        bed = status.get("bed_temper", 0)
        print(f"State: {state}")
        print(f"Progress: {pct}%")
        if remaining:
            print(f"Time remaining: {remaining} min")
        print(f"Nozzle: {nozzle}°C  |  Bed: {bed}°C")
        gcode = status.get("gcode_file", "")
        if gcode:
            print(f"File: {gcode}")
    except BambuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_printer_upload(args) -> int:
    from .bambu import BambuError
    try:
        printer = _get_printer(args)
        print(f"Uploading {args.file}...")
        remote = printer.upload_3mf(args.file)
        print(f"  uploaded to {remote}")
        if args.print:
            print("Starting print...")
            resp = printer.start_print(remote)
            result = resp.get("print", {}).get("result", "unknown")
            print(f"  result: {result}")
    except BambuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_printer_home(args) -> int:
    from .bambu import BambuError
    try:
        printer = _get_printer(args)
        resp = printer.home()
        print("Home:", resp.get("print", {}).get("result", "unknown"))
    except BambuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_printer_stop(args) -> int:
    from .bambu import BambuError
    try:
        printer = _get_printer(args)
        resp = printer.stop_print()
        print("Stop:", resp.get("print", {}).get("result", "unknown"))
    except BambuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
