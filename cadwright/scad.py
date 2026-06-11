"""A clean-room interpreter for a useful subset of the OpenSCAD language.

Supported:
* numbers, booleans, strings, vectors `[a, b, c]`, arithmetic (`+ - * / %`),
  unary minus, parentheses, comparisons, and builtin functions
  (sin/cos/tan/asin/acos/atan/sqrt/abs/min/max/floor/ceil/pow/round) + `PI`.
  Trig is in degrees, matching OpenSCAD.
* variables (`x = 10;`) and `$fn`.
* primitives: cube, sphere, cylinder, polyhedron.
* transforms: translate, rotate, scale, mirror, color (color is a passthrough).
* booleans: union, difference, intersection.
* modules: `module name(a, b=default) { ... }` and calls with children.
* control flow: `for (i = [start:end])` / `[start:step:end]` / `[list]`, and `if/else`.

Not yet supported (raises a clear error): hull, minkowski, linear_extrude,
rotate_extrude, import, functions returning values via `function`. These are the
documented growth edges.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import csg
from .mesh import (Mesh, identity, mat_mul, mirror_m, rotate_xyz, scale_m,
                   translate_m)
from .primitives import cube, cylinder, polyhedron, sphere


class ScadError(Exception):
    pass


# --------------------------------------------------------------------- lexer
_TWO_CHAR = {"<=", ">=", "==", "!=", "&&", "||"}
_PUNCT = set("(){}[],;=+-*/%<>!:.")


@dataclass
class Token:
    kind: str   # num | str | id | op | eof
    value: object
    pos: int


def tokenize(src: str) -> list[Token]:
    toks: list[Token] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and src[j] != '"':
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            toks.append(Token("str", "".join(buf), i))
            i = j + 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            while j < n and (src[j].isdigit() or src[j] in ".eE+-"):
                # stop a trailing +/- that isn't part of an exponent
                if src[j] in "+-" and src[j - 1] not in "eE":
                    break
                j += 1
            toks.append(Token("num", float(src[i:j]), i))
            i = j
            continue
        if c.isalpha() or c == "_" or c == "$":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            toks.append(Token("id", src[i:j], i))
            i = j
            continue
        two = src[i:i + 2]
        if two in _TWO_CHAR:
            toks.append(Token("op", two, i))
            i += 2
            continue
        if c in _PUNCT:
            toks.append(Token("op", c, i))
            i += 1
            continue
        raise ScadError(f"unexpected character {c!r} at {i}")
    toks.append(Token("eof", None, n))
    return toks


# ----------------------------------------------------------------------- AST
@dataclass
class Num:
    value: float


@dataclass
class Str:
    value: str


@dataclass
class Ident:
    name: str


@dataclass
class VectorLit:
    items: list


@dataclass
class Range:
    start: object
    step: object
    end: object


@dataclass
class Unary:
    op: str
    operand: object


@dataclass
class Binary:
    op: str
    left: object
    right: object


@dataclass
class FuncCall:
    name: str
    args: list


@dataclass
class Assign:
    name: str
    expr: object


@dataclass
class ModuleDef:
    name: str
    params: list           # list[(name, default_expr|None)]
    body: list


@dataclass
class ModuleCall:
    name: str
    args: list             # list[(name|None, expr)]
    children: list = field(default_factory=list)


@dataclass
class ForStmt:
    var: str
    iterable: object
    body: list


@dataclass
class IfStmt:
    cond: object
    then: list
    otherwise: list = field(default_factory=list)


# -------------------------------------------------------------------- parser
class Parser:
    def __init__(self, toks: list[Token]):
        self.toks = toks
        self.i = 0

    def peek(self) -> Token:
        return self.toks[self.i]

    def next(self) -> Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, value: str) -> Token:
        t = self.next()
        if t.value != value:
            raise ScadError(f"expected {value!r} but got {t.value!r} at {t.pos}")
        return t

    def at(self, value: str) -> bool:
        return self.peek().value == value

    def parse_program(self) -> list:
        stmts = []
        while self.peek().kind != "eof":
            stmts.append(self.parse_statement())
        return stmts

    def parse_block(self) -> list:
        self.expect("{")
        stmts = []
        while not self.at("}"):
            stmts.append(self.parse_statement())
        self.expect("}")
        return stmts

    def parse_statement(self):
        t = self.peek()
        if t.value == ";":
            self.next()
            return ModuleCall("group", [], [])    # empty
        if t.value == "{":
            return ModuleCall("union", [], self.parse_block())
        if t.kind == "id" and t.value == "module":
            return self.parse_module_def()
        if t.kind == "id" and t.value == "for":
            return self.parse_for()
        if t.kind == "id" and t.value == "if":
            return self.parse_if()
        if t.kind == "id" and self.toks[self.i + 1].value == "=":
            name = self.next().value
            self.expect("=")
            expr = self.parse_expr()
            self.expect(";")
            return Assign(name, expr)
        return self.parse_module_call()

    def parse_module_def(self) -> ModuleDef:
        self.next()                       # 'module'
        name = self.next().value
        self.expect("(")
        params = []
        while not self.at(")"):
            pname = self.next().value
            default = None
            if self.at("="):
                self.next()
                default = self.parse_expr()
            params.append((pname, default))
            if self.at(","):
                self.next()
        self.expect(")")
        body = self.parse_block()
        return ModuleDef(name, params, body)

    def parse_for(self) -> ForStmt:
        self.next()                       # 'for'
        self.expect("(")
        var = self.next().value
        self.expect("=")
        iterable = self.parse_expr()
        self.expect(")")
        body = self.parse_block() if self.at("{") else [self.parse_statement()]
        return ForStmt(var, iterable, body)

    def parse_if(self) -> IfStmt:
        self.next()                       # 'if'
        self.expect("(")
        cond = self.parse_expr()
        self.expect(")")
        then = self.parse_block() if self.at("{") else [self.parse_statement()]
        otherwise = []
        if self.peek().value == "else":
            self.next()
            otherwise = self.parse_block() if self.at("{") else [self.parse_statement()]
        return IfStmt(cond, then, otherwise)

    def parse_module_call(self) -> ModuleCall:
        name = self.next().value
        self.expect("(")
        args = self.parse_call_args()
        self.expect(")")
        children = []
        if self.at("{"):
            children = self.parse_block()
        elif self.at(";"):
            self.next()
        else:
            children = [self.parse_statement()]
        return ModuleCall(name, args, children)

    def parse_call_args(self) -> list:
        args = []
        while not self.at(")"):
            if (self.peek().kind == "id" and self.toks[self.i + 1].value == "="):
                aname = self.next().value
                self.next()               # '='
                args.append((aname, self.parse_expr()))
            else:
                args.append((None, self.parse_expr()))
            if self.at(","):
                self.next()
        return args

    # expressions (precedence climbing)
    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at("||"):
            self.next()
            left = Binary("||", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_cmp()
        while self.at("&&"):
            self.next()
            left = Binary("&&", left, self.parse_cmp())
        return left

    def parse_cmp(self):
        left = self.parse_add()
        while self.peek().value in ("<", ">", "<=", ">=", "==", "!="):
            op = self.next().value
            left = Binary(op, left, self.parse_add())
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.peek().value in ("+", "-"):
            op = self.next().value
            left = Binary(op, left, self.parse_mul())
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.peek().value in ("*", "/", "%"):
            op = self.next().value
            left = Binary(op, left, self.parse_unary())
        return left

    def parse_unary(self):
        if self.peek().value in ("-", "!", "+"):
            op = self.next().value
            return Unary(op, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.next()
        if t.kind == "num":
            return Num(t.value)
        if t.kind == "str":
            return Str(t.value)
        if t.value == "(":
            e = self.parse_expr()
            self.expect(")")
            return e
        if t.value == "[":
            return self.parse_vector_or_range()
        if t.kind == "id":
            if t.value in ("true", "false"):
                return Num(1.0 if t.value == "true" else 0.0)
            if self.at("("):
                self.next()
                args = self.parse_call_args()
                self.expect(")")
                return FuncCall(t.value, [a[1] for a in args])
            return Ident(t.value)
        raise ScadError(f"unexpected token {t.value!r} at {t.pos}")

    def parse_vector_or_range(self):
        first = self.parse_expr()
        if self.at(":"):                  # range [start:end] or [start:step:end]
            self.next()
            second = self.parse_expr()
            step = None
            end = second
            if self.at(":"):
                self.next()
                end = self.parse_expr()
                step = second
            self.expect("]")
            return Range(first, step, end)
        items = [first]
        while self.at(","):
            self.next()
            if self.at("]"):
                break
            items.append(self.parse_expr())
        self.expect("]")
        return VectorLit(items)


# ------------------------------------------------------------------ evaluator
_FUNCS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sqrt": math.sqrt,
    "abs": abs,
    "floor": lambda x: float(math.floor(x)),
    "ceil": lambda x: float(math.ceil(x)),
    "round": lambda x: float(round(x)),
    "ln": math.log,
    "exp": math.exp,
}
_UNSUPPORTED = {"minkowski", "import",
                "surface", "offset", "projection"}
_2D_PRIMITIVES = {"square", "circle", "polygon", "text"}


class Evaluator:
    def __init__(self):
        self.modules: dict[str, ModuleDef] = {}

    # ---- expression evaluation
    def eval_expr(self, node, scope: dict):
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Str):
            return node.value
        if isinstance(node, Ident):
            if node.name == "PI":
                return math.pi
            if node.name in scope:
                return scope[node.name]
            raise ScadError(f"undefined variable: {node.name}")
        if isinstance(node, VectorLit):
            return [self.eval_expr(x, scope) for x in node.items]
        if isinstance(node, Range):
            start = self.eval_expr(node.start, scope)
            end = self.eval_expr(node.end, scope)
            step = self.eval_expr(node.step, scope) if node.step is not None else 1.0
            return _range_list(start, step, end)
        if isinstance(node, Unary):
            v = self.eval_expr(node.operand, scope)
            if node.op == "-":
                return -v
            if node.op == "+":
                return v
            if node.op == "!":
                return 0.0 if v else 1.0
        if isinstance(node, Binary):
            return self._eval_binary(node, scope)
        if isinstance(node, FuncCall):
            if node.name in ("min", "max"):
                vals = [self.eval_expr(a, scope) for a in node.args]
                if len(vals) == 1 and isinstance(vals[0], list):
                    vals = vals[0]
                return (min if node.name == "min" else max)(vals)
            if node.name == "pow":
                a, b = (self.eval_expr(x, scope) for x in node.args)
                return math.pow(a, b)
            if node.name == "len":
                v = self.eval_expr(node.args[0], scope)
                return float(len(v))
            if node.name in _FUNCS:
                return _FUNCS[node.name](self.eval_expr(node.args[0], scope))
            raise ScadError(f"unknown function: {node.name}")
        raise ScadError(f"cannot evaluate node {node!r}")

    def _eval_binary(self, node: Binary, scope: dict):
        op = node.op
        a = self.eval_expr(node.left, scope)
        if op == "&&":
            return a and self.eval_expr(node.right, scope)
        if op == "||":
            return a or self.eval_expr(node.right, scope)
        b = self.eval_expr(node.right, scope)
        if op == "+":
            if isinstance(a, list) and isinstance(b, list):
                return [x + y for x, y in zip(a, b)]
            return a + b
        if op == "-":
            if isinstance(a, list) and isinstance(b, list):
                return [x - y for x, y in zip(a, b)]
            return a - b
        if op == "*":
            if isinstance(a, list) and not isinstance(b, list):
                return [x * b for x in a]
            if isinstance(b, list) and not isinstance(a, list):
                return [a * y for y in b]
            return a * b
        if op == "/":
            return a / b
        if op == "%":
            return math.fmod(a, b)
        if op == "<":
            return 1.0 if a < b else 0.0
        if op == ">":
            return 1.0 if a > b else 0.0
        if op == "<=":
            return 1.0 if a <= b else 0.0
        if op == ">=":
            return 1.0 if a >= b else 0.0
        if op == "==":
            return 1.0 if a == b else 0.0
        if op == "!=":
            return 1.0 if a != b else 0.0
        raise ScadError(f"unknown operator {op}")

    # ---- statement / geometry evaluation
    def eval_block(self, stmts: list, scope: dict) -> Mesh:
        # First bind module defs and assignments, then build geometry.
        local = dict(scope)
        meshes: list[Mesh] = []
        for st in stmts:
            if isinstance(st, ModuleDef):
                self.modules[st.name] = st
            elif isinstance(st, Assign):
                local[st.name] = self.eval_expr(st.expr, local)
        for st in stmts:
            if isinstance(st, (ModuleDef, Assign)):
                continue
            m = self.eval_stmt(st, local)
            if m is not None and not m.is_empty():
                meshes.append(m)
        if not meshes:
            return Mesh()
        out = meshes[0]
        for m in meshes[1:]:
            out = csg.union(out, m)
        return out

    def eval_stmt(self, st, scope: dict) -> Mesh | None:
        if isinstance(st, ForStmt):
            return self._eval_for(st, scope)
        if isinstance(st, IfStmt):
            cond = self.eval_expr(st.cond, scope)
            return self.eval_block(st.then if cond else st.otherwise, scope)
        if isinstance(st, ModuleCall):
            return self.eval_call(st, scope)
        raise ScadError(f"unexpected statement {st!r}")

    def _eval_for(self, st: ForStmt, scope: dict) -> Mesh:
        values = self.eval_expr(st.iterable, scope)
        if not isinstance(values, list):
            values = [values]
        meshes = []
        for val in values:
            inner = dict(scope)
            inner[st.var] = val
            m = self.eval_block(st.body, inner)
            if not m.is_empty():
                meshes.append(m)
        out = Mesh()
        for m in meshes:
            out = csg.union(out, m)
        return out

    def eval_call(self, call: ModuleCall, scope: dict) -> Mesh | None:
        name = call.name
        if name in _UNSUPPORTED:
            raise ScadError(f"'{name}' is not supported yet by the CADwright engine")

        pos, named = [], {}
        for aname, expr in call.args:
            if aname is None:
                pos.append(self.eval_expr(expr, scope))
            else:
                named[aname] = self.eval_expr(expr, scope)

        def fn_facets():
            if "$fn" in named:
                return named["$fn"]
            return scope.get("$fn")

        if name in ("group", "union"):
            return self.eval_block(call.children, scope)
        if name == "difference":
            return self._difference(call.children, scope)
        if name == "intersection":
            return self._intersection(call.children, scope)
        if name in ("translate", "rotate", "scale", "mirror", "color"):
            return self._transform(name, pos, named, call.children, scope)
        if name == "hull":
            return self._hull(call.children, scope)
        if name == "linear_extrude":
            return self._linear_extrude(pos, named, call.children, scope)
        if name == "rotate_extrude":
            return self._rotate_extrude(pos, named, call.children, scope)
        if name in _2D_PRIMITIVES:
            raise ScadError(
                f"2D primitive '{name}' is only valid inside linear_extrude()")

        if name == "cube":
            size = named.get("size", pos[0] if pos else 1.0)
            center = bool(named.get("center", pos[1] if len(pos) > 1 else False))
            return cube(size, center)
        if name == "sphere":
            r = named.get("r", pos[0] if pos else None)
            if r is None and "d" in named:
                r = named["d"] / 2
            return sphere(1.0 if r is None else r, fn=_as_int(fn_facets()))
        if name == "cylinder":
            return self._cylinder(pos, named, fn_facets())
        if name == "polyhedron":
            points = named.get("points", pos[0] if pos else [])
            faces = named.get("faces", pos[1] if len(pos) > 1 else [])
            return polyhedron(points, faces)

        if name in self.modules:
            return self._user_module(self.modules[name], pos, named, scope)
        raise ScadError(f"unknown module/primitive: {name}")

    def _cylinder(self, pos, named, facets) -> Mesh:
        h = named.get("h", pos[0] if pos else 1.0)
        center = bool(named.get("center", False))
        r = named.get("r")
        r1 = named.get("r1")
        r2 = named.get("r2")
        if "d" in named:
            r = named["d"] / 2
        if "d1" in named:
            r1 = named["d1"] / 2
        if "d2" in named:
            r2 = named["d2"] / 2
        if r is None and r1 is None and r2 is None and len(pos) > 1:
            r = pos[1]
        return cylinder(h=h, r=r, r1=r1, r2=r2, center=center, fn=_as_int(facets))

    def _transform(self, name, pos, named, children, scope) -> Mesh:
        child = self.eval_block(children, scope)
        if child.is_empty():
            return child
        if name == "color":
            return child                  # visual only; ignored for geometry
        vec = named.get("v", pos[0] if pos else [0, 0, 0])
        if name == "translate":
            v = _vec3(vec)
            return child.transformed(translate_m(*v))
        if name == "scale":
            v = _vec3(vec, fill=1.0) if isinstance(vec, list) else (vec, vec, vec)
            return child.transformed(scale_m(*v))
        if name == "mirror":
            v = _vec3(vec)
            return child.transformed(mirror_m(*v))
        if name == "rotate":
            if isinstance(vec, list):
                v = _vec3(vec)
                return child.transformed(rotate_xyz(*v))
            angle = vec
            axis = named.get("v", pos[1] if len(pos) > 1 else [0, 0, 1])
            from .mesh import _rot_axis
            return child.transformed(_rot_axis(angle, _vec3(axis)))
        return child

    def _difference(self, children, scope) -> Mesh:
        meshes = [self.eval_stmt(c, scope) for c in children
                  if not isinstance(c, (Assign, ModuleDef))]
        meshes = [m for m in meshes if m is not None and not m.is_empty()]
        if not meshes:
            return Mesh()
        out = meshes[0]
        for m in meshes[1:]:
            out = csg.difference(out, m)
        return out

    def _intersection(self, children, scope) -> Mesh:
        meshes = [self.eval_stmt(c, scope) for c in children
                  if not isinstance(c, (Assign, ModuleDef))]
        meshes = [m for m in meshes if m is not None and not m.is_empty()]
        if not meshes:
            return Mesh()
        out = meshes[0]
        for m in meshes[1:]:
            out = csg.intersection(out, m)
        return out

    def _hull(self, children, scope) -> Mesh:
        from .hull import convex_hull
        verts: list = []
        for c in children:
            if isinstance(c, (Assign, ModuleDef)):
                continue
            m = self.eval_stmt(c, scope)
            if m is not None:
                verts.extend(m.vertices)
        return convex_hull(verts)

    def _linear_extrude(self, pos, named, children, scope) -> Mesh:
        from .shapes2d import extrude
        height = named.get("height", named.get("h", pos[0] if pos else 1.0))
        center = bool(named.get("center", False))
        twist = float(named.get("twist", 0.0))
        slices = named.get("slices")
        outlines = self._collect_2d(children, scope)
        out = Mesh()
        for outline in outlines:
            out.append(extrude(outline, float(height), center=center, twist=twist,
                               slices=int(slices) if slices else None))
        return out

    def _rotate_extrude(self, pos, named, children, scope) -> Mesh:
        from .shapes2d import revolve
        facets = named.get("$fn", scope.get("$fn"))
        out = Mesh()
        for outline in self._collect_2d(children, scope):
            out.append(revolve(outline, int(facets) if facets else 32))
        return out

    def _collect_2d(self, children, scope) -> list:
        outlines = []
        for c in children:
            if isinstance(c, (Assign, ModuleDef)):
                continue
            outlines.extend(self._eval_2d(c, scope))
        return outlines

    def _eval_2d(self, stmt, scope) -> list:
        """Return a list of 2D outlines for a (possibly nested) 2D subtree."""
        from .shapes2d import (square as s2, circle as c2, polygon as p2,
                               text as t2, transform2d)
        if not isinstance(stmt, ModuleCall):
            raise ScadError("expected a 2D primitive child")
        pos, named = [], {}
        for aname, expr in stmt.args:
            if aname is None:
                pos.append(self.eval_expr(expr, scope))
            else:
                named[aname] = self.eval_expr(expr, scope)
        name = stmt.name
        if name == "square":
            size = named.get("size", pos[0] if pos else 1.0)
            center = bool(named.get("center", pos[1] if len(pos) > 1 else False))
            return [s2(size, center)]
        if name == "circle":
            r = named.get("r", pos[0] if pos else None)
            if r is None and "d" in named:
                r = named["d"] / 2
            fn = named.get("$fn", scope.get("$fn"))
            return [c2(1.0 if r is None else r, int(fn) if fn else 32)]
        if name == "polygon":
            return [p2(named.get("points", pos[0] if pos else []))]
        if name == "text":
            s = named.get("text", pos[0] if pos else "")
            size = named.get("size", pos[1] if len(pos) > 1 else 10.0)
            spacing = named.get("spacing", 1.0)
            return t2(s, float(size), float(spacing))
        if name in ("translate", "scale", "rotate", "union", "group"):
            inner = self._collect_2d(stmt.children, scope)
            if name in ("union", "group"):
                return inner
            vec = named.get("v", pos[0] if pos else [0, 0])
            return [transform2d(name, vec, o) for o in inner]
        raise ScadError(f"'{name}' is not a supported 2D child")

    def _user_module(self, mod: ModuleDef, pos, named, scope) -> Mesh:
        inner = dict(scope)
        for idx, (pname, default) in enumerate(mod.params):
            if pname in named:
                inner[pname] = named[pname]
            elif idx < len(pos):
                inner[pname] = pos[idx]
            elif default is not None:
                inner[pname] = self.eval_expr(default, inner)
            else:
                inner[pname] = 0.0
        return self.eval_block(mod.body, inner)


# --------------------------------------------------------------------- helpers
def _as_int(v):
    return int(v) if v is not None else None


def _vec3(v, fill: float = 0.0):
    if not isinstance(v, list):
        return (float(v), float(v), float(v))
    out = [float(x) for x in v]
    while len(out) < 3:
        out.append(fill)
    return (out[0], out[1], out[2])


def _range_list(start, step, end):
    if step == 0:
        return [start]
    out = []
    v = start
    # inclusive of end, tolerant of float drift
    if step > 0:
        while v <= end + 1e-9:
            out.append(v)
            v += step
    else:
        while v >= end - 1e-9:
            out.append(v)
            v += step
    return out


def render_scad(src: str) -> Mesh:
    """Parse + evaluate SCAD source into a Mesh."""
    toks = tokenize(src)
    program = Parser(toks).parse_program()
    return Evaluator().eval_block(program, {})
