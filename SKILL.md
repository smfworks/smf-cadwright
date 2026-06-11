# /cadwright — describe a part, get a printable 3MF

CADwright turns a description (or reference image) into a 3D-printable model
using its own clean-room OpenSCAD-subset engine — no external OpenSCAD install.

## When to use
Trigger when the user wants to **design a 3D-printable part**, mentions
**OpenSCAD / SCAD / 3MF / STL / 3D print**, asks to **model** a bracket, tube,
standoff, plate, knob, enclosure, etc., or wants to **edit** an existing model's
dimensions in plain English.

## How to run

Offline-first (deterministic mock codegen); set `CADWRIGHT_LLM=real` +
`CADWRIGHT_API_BASE/_MODEL/_API_KEY` to drive a real (optionally vision) model.

1. **Generate**
   ```bash
   cadwright gen "<description>" --scad model.scad --preview model.svg --out model.3mf
   ```
   Show the user the SVG preview and the parametric SCAD.

2. **Refine** (loop) — translate the user's plain-English change into an edit:
   ```bash
   cadwright shell        # then: edit make it 6mm thick   /   edit set hole_d = 4.3
   ```
   Re-show the preview after each change.

3. **Export** the final `.3mf` (and `.stl` if asked) for the user's slicer.

## Guidance
- Always keep dimensions as **named variables** so edits are quick re-tunes.
- 3MF is millimetres, slicer-ready. Offer STL as an alternative.
- If the user asks for an unsupported feature (`hull`, `linear_extrude`,
  `rotate_extrude`, `minkowski`, `import`, `text`), say it's a known growth edge
  and offer a primitive/boolean approximation.
- For image input, pass `--image <path>` (used by real vision providers).
