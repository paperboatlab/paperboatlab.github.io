"""Render Paperboat block graphics (compact plate and original card) as HTML + SVG.

Mirrors the web UI's block rendering rules (`paperboat-shared/src/icon.ts`, `Compact.tsx`,
`ports.ts`, `poly.ts`, and `apps/web/src/Block.tsx`) so generated toolkit documentation
pages show accurate previews in both light and dark themes without browser dependencies.
"""

from __future__ import annotations

import html
import math
import re
from typing import Any

STROKE = {
    "ink": "var(--pb-ink)",
    "muted": "var(--pb-line-strong)",
    "signal": "var(--pb-signal)",
    "electrical": "var(--pb-dom-electrical, var(--pb-ink))",
    "translational": "var(--pb-dom-translational, var(--pb-ink))",
    "thermal": "var(--pb-dom-thermal, var(--pb-ink))",
    "fluid": "var(--pb-dom-fluid, var(--pb-ink))",
    "magnetic": "var(--pb-dom-magnetic, var(--pb-ink))",
    "rotational": "var(--pb-dom-rotational, var(--pb-ink))",
}
WEIGHT = {"thin": 1, "normal": 1.5, "wire": 2}
DASH = {"solid": "none", "axis": "2 2", "dash": "5 3", "dot": "1 2", "dashdot": "5 2 1 2"}
FILL = {
    "none": "none",
    "ink": "var(--pb-ink)",
    "raised": "var(--pb-surface-raised)",
    "sunken": "var(--pb-surface-sunken)",
    "signal": "var(--pb-signal)",
    "screen": "var(--pb-surface-screen)",
    "electrical": "var(--pb-dom-electrical, var(--pb-ink))",
    "translational": "var(--pb-dom-translational, var(--pb-ink))",
    "thermal": "var(--pb-dom-thermal, var(--pb-ink))",
    "fluid": "var(--pb-dom-fluid, var(--pb-ink))",
    "magnetic": "var(--pb-dom-magnetic, var(--pb-ink))",
    "rotational": "var(--pb-dom-rotational, var(--pb-ink))",
}
CORNER = {"0": 0, "sm": 3, "md": 5}
FONT = {"sans": "var(--pb-font-sans)", "mono": "var(--pb-font-mono)"}
SIZES = {12, 12.5, 13, 15, 30}
CELL = {"w": 64, "h": 56}
PAD = 8

SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
BUILTINS = {
    "pi", "e", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "exp", "log", "log10", "sqrt", "abs",
    "floor", "ceil", "round", "sign", "frac", "min", "max", "clamp", "mod", "pow",
}
TOKEN_RE = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|([A-Za-z_]\w*)(\s*\()?")
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\{([^}]+)\}")
CAPTION_RE = re.compile(r"\{(\w+)(:poly)?\}")


def _esc(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _fmt_num(val: float, precision: int = 4) -> str:
    rounded = round(float(val), precision)
    if rounded == 0:
        return "0"
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{precision}f}".rstrip("0").rstrip(".")


def _show_param(val: Any) -> str:
    if isinstance(val, dict):
        if "var" in val:
            return str(val["var"])
        if "expr" in val:
            return f"ƒ {val['expr']}"
    if isinstance(val, bool):
        return "on" if val else "off"
    if isinstance(val, (int, float)):
        return _fmt_num(val).replace("-", "−")
    return "" if val is None else str(val)


def polynomial(text: str, var: str = "s") -> str:
    """Format space- or comma-separated coefficients as a descending-power polynomial."""
    stripped = text.strip()
    if not stripped:
        return text
    parts = re.split(r"[\s,]+", stripped)
    try:
        coeffs = [float(p) for p in parts]
    except ValueError:
        return text
    if any(not math.isfinite(c) for c in coeffs):
        return text
    terms: list[str] = []
    for i, c in enumerate(coeffs):
        power = len(coeffs) - 1 - i
        if c == 0:
            continue
        mag = abs(c)
        coeff = "" if (power > 0 and mag == 1) else _fmt_num(mag)
        if power == 0:
            term = _fmt_num(mag)
        elif power == 1:
            term = f"{coeff}{var}"
        else:
            sup = "".join(SUP[int(d)] for d in str(power))
            term = f"{coeff}{var}{sup}"
        if terms:
            terms.append(f"{'−' if c < 0 else '+'} {term}")
        else:
            terms.append(f"{'−' if c < 0 else ''}{term}")
    return " ".join(terms) if terms else "0"


def caption_value(template: str | None, params: dict[str, Any]) -> str:
    """Fill `{id}` and `{id:poly}` placeholders from parameter defaults."""
    if not template:
        return ""
    domain = params.get("domain") if isinstance(params.get("domain"), str) else "s"

    def repl(m: re.Match[str]) -> str:
        key, poly = m.group(1), m.group(2)
        val = params.get(key)
        shown = _show_param(val)
        if poly and not isinstance(val, dict):
            return polynomial(shown, domain)
        return shown

    return CAPTION_RE.sub(repl, template)


def parse_signs(text: Any) -> list[int]:
    """Extract `+1` / `-1` per sign character, defaulting to `++`."""
    signs = [
        1 if c == "+" else -1
        for c in ("" if text is None else str(text))
        if c in ("+", "-", "\u2212")
    ][:26]
    return signs or [1, 1]


def parse_placeholders(text: Any) -> list[str]:
    """Extract unique `{placeholder}` names in order, skipping `{{` and `}}`."""
    out: list[str] = []
    seen: set[str] = set()
    for m in PLACEHOLDER_RE.finditer("" if text is None else str(text)):
        if m.group(1) is None:
            continue
        name = m.group(1).strip()
        if name and "{" not in name and "}" not in name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def parse_inputs(text: Any) -> list[str]:
    """Extract free variable names from an expression param in first-appearance order."""
    if not isinstance(text, str):
        return []
    out: list[str] = []
    for m in TOKEN_RE.finditer(text):
        name, call = m.group(1), m.group(2)
        if name and not call and name not in BUILTINS and name not in out:
            out.append(name)
    return out


def parse_names(text: Any, reserved: list[str]) -> list[str]:
    """Extract valid identifier names up to 64 entries, skipping reserved ids."""
    out: list[str] = []
    for name in re.split(r"[\s,]+", "" if text is None else str(text)):
        if re.match(r"^[A-Za-z_]\w*$", name) and name not in out and name not in reserved and len(out) < 64:
            out.append(name)
    return out


def _name_ports(
    side: list[dict[str, Any]],
    other: list[dict[str, Any]],
    text: Any,
    unit_text: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    names = parse_names(text, [p["id"] for p in other])
    units = [u for u in re.split(r"[\s,]+", "" if unit_text is None else str(unit_text)) if u]
    proto = dict(side[0]) if side else {"id": "a"}
    proto.pop("unit", None)

    def unit_of(i: int) -> str | None:
        return units[i] if i < len(units) and units[i] != "-" else None

    ports = []
    for i, pid in enumerate(names):
        entry = {**proto, "id": pid}
        u = unit_of(i)
        if u:
            entry["unit"] = u
        ports.append(entry)
    return ports, other


def default_params(block: dict[str, Any]) -> dict[str, Any]:
    """Return `{param_id: default}` for a block definition."""
    return {p["id"]: p.get("default") for p in block.get("params", [])}


def in_form(block: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Resolve dynamic ports (`forms`, `ports_from`, `inputs_from`, `outputs_from`) from params."""
    out = dict(block)
    forms = block.get("forms") or []
    if forms:
        picked = next((f for f in forms if f.get("name") == params.get("form")), None)
        if picked:
            out["inputs"] = picked.get("inputs", [])
            out["outputs"] = picked.get("outputs", [])
    inputs = list(out.get("inputs", []))
    outputs = list(out.get("outputs", []))

    if block.get("outputs_from"):
        outputs, inputs = _name_ports(outputs, inputs, params.get(block["outputs_from"]), params.get("units"))

    ports_from = block.get("ports_from")
    if ports_from == "names":
        inputs, outputs = _name_ports(inputs, outputs, params.get(ports_from), params.get("units"))
    elif ports_from == "template":
        tmpl = params.get("template")
        if tmpl is None:
            tmpl = "Hello {name}"
        inputs = [{"id": name, "type": "any"} for name in parse_placeholders(tmpl)]
    elif ports_from:
        raw = params.get(ports_from)
        if ports_from == "inputs" or (isinstance(raw, (int, float)) and not isinstance(raw, bool)):
            count_val = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 2.0
            count = max(1, min(26, int(math.floor(count_val))))
            proto = inputs[0] if inputs else {"id": "a"}
            inputs = [{**proto, "id": chr(97 + i)} for i in range(count)]
        else:
            proto = inputs[0] if inputs else {"id": "a"}
            inputs = [{**proto, "id": chr(97 + i)} for i, _ in enumerate(parse_signs(raw))]

    if block.get("inputs_from"):
        proto = inputs[0] if inputs else {"id": "t", "type": "signal"}
        inputs = [{**proto, "id": pid} for pid in parse_inputs(params.get(block["inputs_from"]))]

    out["inputs"] = inputs
    out["outputs"] = outputs
    return out


def sign_of(block: dict[str, Any], params: dict[str, Any], index: int) -> str:
    """Return `+` or `−` for a `signs`-driven input port, else empty string."""
    if block.get("ports_from") != "signs":
        return ""
    signs = parse_signs(params.get("signs"))
    if index >= len(signs):
        return ""
    return "−" if signs[index] < 0 else "+"


def has_step_ports(block: dict[str, Any]) -> bool:
    return any(p.get("type") == "step" for p in [*block.get("inputs", []), *block.get("outputs", [])])


def _on_grid(n: Any) -> bool:
    return isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and 0 <= n <= 100 and n % 5 == 0


def _prim_valid(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    if "stroke" in p and p["stroke"] not in STROKE:
        return False
    if "weight" in p and p["weight"] not in WEIGHT:
        return False
    if "dash" in p and p["dash"] not in DASH:
        return False
    if "fill" in p and p["fill"] not in FILL:
        return False
    if "when" in p and p["when"] not in ("on", "off"):
        return False
    t = p.get("t")
    if t in ("line", "poly"):
        pts = p.get("p")
        return isinstance(pts, list) and len(pts) >= 2 and all(
            isinstance(pt, list) and len(pt) == 2 and _on_grid(pt[0]) and _on_grid(pt[1]) for pt in pts
        )
    if t == "rect":
        return all(_on_grid(p.get(k)) for k in ("x", "y", "w", "h")) and (
            "corner" not in p or str(p["corner"]) in CORNER
        )
    if t == "ellipse":
        return all(_on_grid(p.get(k)) for k in ("x", "y", "w", "h"))
    if t == "arc":
        return (
            all(_on_grid(p.get(k)) for k in ("x", "y", "w", "h"))
            and isinstance(p.get("a0"), (int, float))
            and isinstance(p.get("a1"), (int, float))
            and math.isfinite(p["a0"])
            and math.isfinite(p["a1"])
        )
    if t == "text":
        return (
            _on_grid(p.get("x"))
            and _on_grid(p.get("y"))
            and isinstance(p.get("s"), str)
            and ("font" not in p or p["font"] in FONT)
            and ("size" not in p or p["size"] in SIZES)
        )
    return False


def icon_valid(icon: Any) -> bool:
    """Return True when `view.icon` passes the renderer's grid and token rules."""
    if not isinstance(icon, dict) or not isinstance(icon.get("g"), list):
        return False
    w = icon.get("w", 1)
    h = icon.get("h", 1)
    if w not in (1, 2) or h not in (1, 2) or (w == 2 and h == 2):
        return False
    return all(_prim_valid(p) for p in icon["g"])


def plate_size(icon: dict[str, Any]) -> tuple[int, int]:
    return CELL["w"] * int(icon.get("w", 1)), CELL["h"] * int(icon.get("h", 1))


def has_compact_plate(eff_block: dict[str, Any]) -> bool:
    """Match `Block.tsx`: compact plates apply when `view.compact` or valid `view.icon`, unless step ports exist."""
    view = eff_block.get("view") or {}
    return bool(view.get("compact") or icon_valid(view.get("icon"))) and not has_step_ports(eff_block)


def _r(n: float) -> str:
    val = round(n, 2)
    return str(int(val)) if val == int(val) else f"{val:.2f}".rstrip("0").rstrip(".")


def _svg_attrs(attrs: dict[str, Any]) -> str:
    return " ".join(f'{k}="{_esc(v)}"' for k, v in attrs.items())


def icon_svg(icon: dict[str, Any], params: dict[str, Any], on: bool = False) -> str:
    """Render a validated `view.icon` into an inline `<svg class="pb-icon-art">`."""
    w, h = plate_size(icon)
    sx = (w - 2 * PAD) / 100.0
    sy = (h - 2 * PAD) / 100.0
    X = lambda x: _r(PAD + x * sx)
    Y = lambda y: _r(PAD + y * sy)
    parts: list[str] = []

    for p in icon["g"]:
        when = p.get("when")
        if when and (when == "on") != on:
            continue
        stroke = STROKE[p.get("stroke", "ink")]
        weight = WEIGHT[p.get("weight", "normal")]
        dash = DASH[p.get("dash", "solid")]
        fill = FILL[p.get("fill", "none")]
        line_attrs = {
            "stroke": stroke,
            "stroke-width": weight,
            "stroke-dasharray": dash,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        }
        body_attrs = {**line_attrs, "fill": fill}
        t = p["t"]
        if t == "line":
            pts = " ".join(f"{X(x)},{Y(y)}" for x, y in p["p"])
            parts.append(f'<polyline {_svg_attrs({**line_attrs, "fill": "none", "points": pts})}/>')
        elif t == "poly":
            pts = " ".join(f"{X(x)},{Y(y)}" for x, y in p["p"])
            parts.append(f'<polygon {_svg_attrs({**body_attrs, "points": pts})}/>')
        elif t == "rect":
            rx = CORNER[str(p.get("corner", "0"))]
            attrs = {**body_attrs, "x": X(p["x"]), "y": Y(p["y"]), "width": _r(p["w"] * sx), "height": _r(p["h"] * sy), "rx": rx}
            parts.append(f"<rect {_svg_attrs(attrs)}/>")
        elif t == "ellipse":
            attrs = {
                **body_attrs,
                "cx": X(p["x"] + p["w"] / 2),
                "cy": Y(p["y"] + p["h"] / 2),
                "rx": _r((p["w"] / 2) * sx),
                "ry": _r((p["h"] / 2) * sy),
            }
            parts.append(f"<ellipse {_svg_attrs(attrs)}/>")
        elif t == "arc":
            cx, cy = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2
            rx, ry = p["w"] / 2, p["h"] / 2
            at = lambda a: f"{X(cx + rx * math.cos(math.radians(a)))},{Y(cy - ry * math.sin(math.radians(a)))}"
            sweep = ((p["a1"] - p["a0"]) % 360 + 360) % 360
            large = 1 if sweep > 180 else 0
            d = f"M{at(p['a0'])}A{_r(rx * sx)},{_r(ry * sy)} 0 {large} 0 {at(p['a1'])}"
            parts.append(f'<path {_svg_attrs({**body_attrs, "d": d})}/>')
        elif t == "text":
            attrs = {
                "x": X(p["x"]),
                "y": Y(p["y"]),
                "fill": stroke,
                "stroke": "none",
                "text-anchor": "middle",
                "dominant-baseline": "central",
                "font-family": FONT[p.get("font", "sans")],
                "font-size": p.get("size", 12),
            }
            text = caption_value(p["s"], params)
            parts.append(f"<text {_svg_attrs(attrs)}>{_esc(text)}</text>")

    return f'<svg class="pb-icon-art" width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">{"".join(parts)}</svg>'


def _handle_html(port: dict[str, Any], dir_name: str, side: str, style: str = "") -> str:
    ptype = port.get("type") or "signal"
    kind_cls = "target" if dir_name == "in" else "source"
    style_attr = f' style="{_esc(style)}"' if style else ""
    return f'<i class="pb-handle {kind_cls} side-{side} t-{_esc(ptype)}"{style_attr} aria-hidden="true"></i>'


def _icon_ports_html(icon: dict[str, Any], params: dict[str, Any], connectors: dict[str, Any] | None) -> str:
    out: list[str] = []
    for port in icon.get("ports") or []:
        if port.get("if") is not None and not params.get(port["if"]):
            continue
        c = (connectors or {}).get(port.get("class", ""), {})
        side = port.get("side", "left")
        at = port.get("at", 50)
        along = f"top:{at}%" if side in ("left", "right") else f"left:{at}%"
        fill = "filled" if (port.get("variant") or c.get("alt")) == "filled" else "hollow"
        handle = c.get("handle", "circle")
        size = c.get("size", 8)
        kind = c.get("kind", "output")
        color_style = f"--ip-color:{_esc(c['color'])};" if c.get("color") else ""
        cls = f"pb-handle side-{side} ip ip-{_esc(handle)} ip-{_esc(size)} ip-{fill} k-{_esc(kind)}"
        out.append(f'<i class="{cls}" style="{along};{color_style}" aria-hidden="true"></i>')
    return "".join(out)


def render_compact_plate(block: dict[str, Any], params: dict[str, Any], connectors: dict[str, Any] | None = None) -> str:
    """Render a block's compact plate graphic (`.pb-compact-block`)."""
    view = block.get("view") or {}
    icon = view.get("icon") if icon_valid(view.get("icon")) else None
    size_style = ""
    if icon:
        w, h = plate_size(icon)
        size_style = f' style="width:{w}px;height:{h}px"'
        art = icon_svg(icon, params, on=False)
    else:
        glyph = caption_value(view.get("glyph"), params) if view.get("glyph") else "const"
        font_size = 10.5 if len(glyph) > 5 else (13 if len(glyph) > 3 else 17)
        art = (
            '<svg class="pb-glyph" viewBox="0 0 30 30" aria-hidden="true">'
            f'<text x="15" y="15" text-anchor="middle" dominant-baseline="central" style="font-size:{font_size}px">{_esc(glyph)}</text>'
            "</svg>"
        )

    if icon and icon.get("ports"):
        ports_html = _icon_ports_html(icon, params, connectors)
    else:
        chunks: list[str] = []
        for side, dir_name, ports in (
            ("left", "in", block.get("inputs", [])),
            ("right", "out", block.get("outputs", [])),
        ):
            n = len(ports)
            for i, p in enumerate(ports):
                coord = f"{((i + 1) / (n + 1)) * 100:.4f}".rstrip("0").rstrip(".") + "%"
                chunks.append(_handle_html(p, dir_name, side, f"top:{coord}"))
                if dir_name == "in":
                    s = sign_of(block, params, i)
                    if s:
                        chunks.append(f'<span class="pb-plate-sign" style="top:{coord}" aria-hidden="true">{_esc(s)}</span>')
        ports_html = "".join(chunks)

    label = block.get("label") or block.get("type", "")
    value = caption_value(view.get("value"), params)
    val_html = f'<span class="pb-plate-val">{_esc(value)}</span>' if value else ""
    return (
        f'<div class="pb-compact-block kind-{_esc(block.get("kind", "function"))}">'
        f'<div class="pb-plate"{size_style}>{art}{ports_html}</div>'
        f'<div class="pb-plate-cap"><span>{_esc(label)}</span>{val_html}</div>'
        "</div>"
    )


def _param_value_html(p: dict[str, Any], value: Any) -> str:
    ptype = p.get("type", "number")
    if ptype == "boolean":
        checked = value is True or value == 1
        return f'<span class="pb-bool{" checked" if checked else ""}" aria-hidden="true"></span>'
    if ptype == "enum":
        return f'<span class="pb-enum">{_esc(value)}</span>'
    if ptype in ("file", "text", "variable", "matrix"):
        return f'<span class="pb-param-val text-param">{_esc("" if value is None else value)}</span>'
    if ptype == "key":
        return f'<span class="pb-param-val key-param">{_esc("" if value is None else value)}</span>'
    shown = _fmt_num(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else ("" if value is None else str(value))
    return f'<span class="pb-param-val">{_esc(shown)}</span>'


def render_original_block(block: dict[str, Any], params: dict[str, Any]) -> str:
    """Render a block's original card graphic (`.pb-block`)."""
    step = has_step_ports(block)
    kind = block.get("kind", "function")
    tag = "step" if step else ("fn" if kind == "function" else kind)
    classes = ["pb-block", f"kind-{_esc(kind)}"]
    if step:
        classes.append("step")

    inputs = block.get("inputs", [])
    outputs = block.get("outputs", [])
    rows_html: list[str] = []
    for i in range(max(len(inputs), len(outputs))):
        left = "<span></span>"
        right = "<span></span>"
        if i < len(inputs):
            p = inputs[i]
            ptype = p.get("type") or "signal"
            s = sign_of(block, params, i)
            sign_html = f'<span class="pb-port-sign">{_esc(s)}</span>' if s else ""
            unit_html = f'<span class="pb-unit"> {_esc(p["unit"])}</span>' if p.get("unit") else ""
            left = (
                f'<div class="pb-port in side-left port-{_esc(ptype)}">'
                f'{_handle_html(p, "in", "left")}{_esc(p["id"])}{sign_html}{unit_html}'
                "</div>"
            )
        if i < len(outputs):
            p = outputs[i]
            ptype = p.get("type") or "signal"
            unit_html = f'<span class="pb-unit">{_esc(p["unit"])} </span>' if p.get("unit") else ""
            right = (
                f'<div class="pb-port out side-right port-{_esc(ptype)}">'
                f'{unit_html}{_esc(p["id"])}{_handle_html(p, "out", "right")}'
                "</div>"
            )
        rows_html.append(f'<div class="pb-port-row">{left}{right}</div>')

    params_html: list[str] = []
    for p in block.get("params", []):
        unit_html = f'<span class="pb-unit"> {_esc(p["unit"])}</span>' if p.get("unit") else ""
        val_html = _param_value_html(p, params.get(p["id"]))
        params_html.append(
            f'<div class="pb-param"><span>{_esc(p["id"])}{unit_html}</span>{val_html}</div>'
        )

    label = block.get("label") or block.get("type", "")
    return (
        f'<div class="{" ".join(classes)}">'
        '<div class="pb-block-title">'
        f'<span class="pb-block-name">{_esc(label)}</span>'
        f'<span class="pb-block-tag">{_esc(tag)}</span>'
        "</div>"
        f'{"".join(rows_html)}{"".join(params_html)}'
        "</div>"
    )


def render_block_preview(block: dict[str, Any], connectors: dict[str, Any] | None = None) -> str:
    """Render the block preview stage: both compact plate and original card when compact, else original card."""
    params = default_params(block)
    eff = in_form(block, params)
    items: list[str] = []
    if has_compact_plate(eff):
        plate = render_compact_plate(eff, params, connectors)
        card = render_original_block(eff, params)
        items.append(f'<div class="pb-preview-item">{plate}<span class="pb-preview-label">Compact plate</span></div>')
        items.append(f'<div class="pb-preview-item">{card}<span class="pb-preview-label">Original</span></div>')
    else:
        card = render_original_block(eff, params)
        items.append(f'<div class="pb-preview-item">{card}</div>')
    return f'<div class="pb-block-preview" role="img" aria-label="{_esc(block.get("label") or block.get("type", "Block"))} block graphic">{"".join(items)}</div>'
