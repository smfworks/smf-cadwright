# CADwright

**Describe a part → get a 3D-printable file.** CADwright is an OpenClaw add-on
that turns a natural-language description (or a reference image) into a
parametric model and exports **3MF** for your slicer — all in one place. No
copy-pasting between a web AI and a desktop CAD app.

It ships its **own clean-room OpenSCAD-subset engine** — parser → CSG → mesh →
3MF — so there's **no external OpenSCAD install** and **no GPL** (we own the
engine). Runs **fully offline** by default with deterministic mock codegen.

```
prompt / image
   ↓  AI codegen      → parametric OpenSCAD (dimensions = named variables)
   ↓  our SCAD engine → mesh  (cube/sphere/cylinder/polyhedron, transforms,
   ↓                           union/difference/intersection, modules, for/if)
   ↓  preview         → SVG (isometric, shaded)
   ↓  edit in English ("make it 6mm thick") → re-render
   ↓  export          → model.3mf  (+ STL)
```

## Quick start

```bash
cd cadwright
pip install -e ".[dev]"     # or just run: python -m cadwright.cli ...
python demo.py              # offline demo: builds + exports a few parts
pytest -q                   # 22 tests
```

## CLI

```bash
# one-shot generate + export
cadwright gen "an M3 standoff, outer 8mm, inner 3.2mm, 12mm tall" --out standoff.3mf --preview standoff.svg

# generate a plate with holes, save the SCAD too
cadwright gen "a 50mm wide 30mm deep plate, 4mm thick, with M4 holes" --scad plate.scad --out plate.3mf

# render an existing .scad through our engine
cadwright render plate.scad --out plate.3mf --preview plate.svg

# model from a photo (needs a real vision model — see below)
cadwright gen "model this part" --image part.jpg --out part.3mf

# interactive: describe -> refine -> export
cadwright shell
  cadwright> a 24mm diameter knob, 10mm tall
  cadwright> edit make it 18mm tall
  cadwright> export knob.3mf
```

| Command | What it does |
|---|---|
| `cadwright gen "<desc>"` | generate parametric SCAD → mesh; optional `--out/.3mf`, `--stl`, `--preview/.svg`, `--scad` |
| `cadwright render <file.scad>` | run an existing SCAD file through the engine + export |
| `cadwright shell` | interactive generate → `edit <change>` → `export <file>` loop |

## Supported SCAD subset (our engine)

- **Primitives:** `cube`, `sphere`, `cylinder` (incl. cones via `r1/r2`/`d1/d2`), `polyhedron`
- **Transforms:** `translate`, `rotate`, `scale`, `mirror`, `color` (passthrough)
- **Booleans:** `union`, `difference`, `intersection`
- **Hull:** `hull()` — 3D convex hull of its children (rounded/organic parts)
- **2D + extrude:** `square`, `circle`, `polygon` profiles + `linear_extrude(height, center, twist, slices)`
- **Lathe:** `rotate_extrude($fn)` — revolve a profile 360° about Z (vases, pulleys, rings)
- **2D booleans / holes:** `union`/`difference`/`intersection` of 2D profiles inside an extrude — e.g. a washer is `difference(){ circle(10); circle(4); }` extruded
- **Offset:** `offset(r=)`/`offset(delta=)` grows/shrinks a profile (shells, clearances) — miter join
- **Text:** `text("LABEL", size)` via a built-in 5×7 vector font — use inside `linear_extrude` for embossed labels
- **Language:** variables, `$fn`, arithmetic, vectors, comparisons, `module`s with
  defaults, `for` (ranges `[a:b]`/`[a:step:b]` and lists), `if/else`, builtins
  (`sin/cos/tan/sqrt/abs/min/max/floor/ceil/pow/round`, `PI`; trig in degrees)
- **Exports:** **3MF** (mm, slicer-ready) and binary **STL**

**Documented growth edges** (raise a clear error today): `minkowski`,
`import`, `projection`, `surface`.

## Real model (optional)

Offline mock codegen needs no setup. To drive a real model for richer prompts
and image input, set an OpenAI-compatible endpoint:

```bash
setx CADWRIGHT_LLM   real
setx CADWRIGHT_API_BASE  https://openrouter.ai/api/v1   # or Ollama/OpenAI/etc.
setx CADWRIGHT_MODEL     openai/gpt-4o-mini
setx CADWRIGHT_API_KEY   <key>
```

The codegen emits **parametric** SCAD (named dimension variables), so the
plain-English edit loop just retunes variables and re-renders.

## Image input (photo → model)

Pass a reference photo and a **vision-capable** model turns it into parametric
SCAD:

```bash
cadwright gen "model this knob" --image knob.jpg --out knob.3mf
# or in the shell:
cadwright shell
  cadwright> image knob.jpg
  cadwright> a knob about 30mm across     # text dims override the photo
  cadwright> edit make it 18mm tall
  cadwright> export knob.3mf
```

The image is sent as a base64 data URL in the OpenAI-compatible multimodal
format, so any vision model behind `CADWRIGHT_API_BASE` (e.g. `gpt-4o`,
`gpt-4o-mini`, a vision-capable OpenRouter/Ollama model) works. Offline mock
mode can't see the image — it falls back to the text prompt and says so.

## How it fits OpenClaw

CADwright is usable as a `/cadwright` skill (see `SKILL.md`): a guided
describe → preview → refine → export flow that owns the whole pipeline and hands
you a `.3mf` ready for your printer.
