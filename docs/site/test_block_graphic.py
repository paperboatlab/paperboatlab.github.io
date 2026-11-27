"""Unit tests for docs/site/block_graphic.py and helpjson._summary."""

from __future__ import annotations

import sys
from pathlib import Path

from docutils import nodes

sys.path.insert(0, str(Path(__file__).resolve().parent))

from block_graphic import (  # noqa: E402
    caption_value,
    default_params,
    has_compact_plate,
    icon_svg,
    icon_valid,
    in_form,
    polynomial,
    render_block_preview,
)
from helpjson import _summary  # noqa: E402


def test_polynomial_formatting():
    assert polynomial("1 2 1", "s") == "s² + 2s + 1"
    assert polynomial("1 0 -4", "z") == "z² − 4"
    assert polynomial("0 0", "s") == "0"
    assert polynomial("not numbers", "s") == "not numbers"


def test_caption_value():
    params = {"k": 2.0, "min": -1.5, "max": 3.0, "num": "1 0", "den": "1 2 1", "domain": "s"}
    assert caption_value("{k}", params) == "2"
    assert caption_value("{min}…{max}", params) == "−1.5…3"
    assert caption_value("{num:poly}", params) == "s"
    assert caption_value("{den:poly}", params) == "s² + 2s + 1"


def test_in_form_dynamic_ports():
    sum_block = {
        "type": "sum",
        "label": "Sum",
        "kind": "function",
        "inputs": [{"id": "a", "type": "signal"}],
        "outputs": [{"id": "y", "type": "signal"}],
        "params": [{"id": "signs", "type": "text", "default": "+-+"}],
        "ports_from": "signs",
    }
    eff_sum = in_form(sum_block, default_params(sum_block))
    assert [p["id"] for p in eff_sum["inputs"]] == ["a", "b", "c"]

    fmt_block = {
        "type": "format",
        "label": "Format",
        "kind": "function",
        "inputs": [],
        "outputs": [{"id": "y", "type": "text"}],
        "params": [{"id": "template", "type": "text", "default": "Hello {name} ({count})"}],
        "ports_from": "template",
    }
    eff_fmt = in_form(fmt_block, default_params(fmt_block))
    assert [p["id"] for p in eff_fmt["inputs"]] == ["name", "count"]

    fn_block = {
        "type": "function",
        "label": "f(t)",
        "kind": "function",
        "inputs": [{"id": "t", "type": "signal"}],
        "outputs": [{"id": "y", "type": "signal"}],
        "params": [{"id": "f", "type": "text", "default": "sin(x) + k * cos(t)"}],
        "inputs_from": "f",
    }
    eff_fn = in_form(fn_block, default_params(fn_block))
    assert [p["id"] for p in eff_fn["inputs"]] == ["x", "k", "t"]

    cmp_block = {
        "type": "compare",
        "label": "Compare",
        "kind": "function",
        "inputs": [{"id": "a", "type": "signal"}, {"id": "b", "type": "signal"}],
        "outputs": [{"id": "y", "type": "signal"}],
        "params": [{"id": "form", "type": "enum", "default": "step", "options": ["signal", "step"]}],
        "forms": [
            {"name": "signal", "inputs": [{"id": "a", "type": "signal"}, {"id": "b", "type": "signal"}], "outputs": [{"id": "y", "type": "signal"}]},
            {"name": "step", "inputs": [{"id": "in", "type": "step"}, {"id": "a", "type": "signal"}], "outputs": [{"id": "then", "type": "step"}]},
        ],
    }
    eff_cmp = in_form(cmp_block, default_params(cmp_block))
    assert [p["id"] for p in eff_cmp["outputs"]] == ["then"]
    assert not has_compact_plate(eff_cmp)


def test_icon_svg_all_primitives_and_when_filter():
    icon = {
        "w": 2,
        "h": 1,
        "g": [
            {"t": "line", "p": [[10, 50], [90, 50]], "stroke": "muted", "weight": "thin"},
            {"t": "poly", "p": [[20, 20], [50, 80], [80, 20]], "fill": "screen"},
            {"t": "rect", "x": 15, "y": 15, "w": 20, "h": 20, "corner": "sm"},
            {"t": "ellipse", "x": 40, "y": 40, "w": 20, "h": 20, "when": "off"},
            {"t": "ellipse", "x": 40, "y": 40, "w": 20, "h": 20, "fill": "signal", "when": "on"},
            {"t": "arc", "x": 20, "y": 20, "w": 40, "h": 40, "a0": 0, "a1": 180},
            {"t": "text", "x": 50, "y": 30, "s": "{num:poly}", "font": "mono", "size": 13},
        ],
    }
    assert icon_valid(icon)
    svg = icon_svg(icon, {"num": "1 2"}, on=False)
    assert 'width="128" height="56"' in svg
    assert "<polyline " in svg
    assert "<polygon " in svg
    assert "<rect " in svg
    assert "<ellipse " in svg
    assert "<path " in svg
    assert "s + 2</text>" in svg
    assert "var(--pb-signal)" not in svg  # when="on" primitive excluded at rest


def test_render_block_preview_both_and_original_only():
    compact_block = {
        "type": "transfer_fn",
        "label": "Transfer Function",
        "kind": "function",
        "inputs": [{"id": "u", "type": "signal", "unit": "V"}],
        "outputs": [{"id": "y", "type": "signal", "unit": "m"}],
        "params": [
            {"id": "num", "type": "text", "default": "1"},
            {"id": "den", "type": "text", "default": "1 1"},
            {"id": "realize", "type": "enum", "default": "solver", "options": ["solver", "tustin"]},
            {"id": "steady", "type": "boolean", "default": False},
        ],
        "view": {
            "compact": True,
            "icon": {
                "w": 2,
                "h": 1,
                "g": [
                    {"t": "text", "x": 50, "y": 30, "s": "{num:poly}", "font": "mono", "size": 13},
                    {"t": "line", "p": [[10, 50], [90, 50]]},
                    {"t": "text", "x": 50, "y": 70, "s": "{den:poly}", "font": "mono", "size": 13},
                ],
            },
        },
    }
    html_both = render_block_preview(compact_block)
    assert "pb-compact-block" in html_both
    assert "pb-block " in html_both
    assert "Compact plate" in html_both
    assert "Original" in html_both
    assert "s + 1</text>" in html_both
    assert "pb-enum" in html_both
    assert "pb-bool" in html_both

    step_block = {
        "type": "start",
        "label": "Start",
        "kind": "source",
        "inputs": [],
        "outputs": [{"id": "out", "type": "step"}],
        "params": [],
    }
    html_orig = render_block_preview(step_block)
    assert "pb-compact-block" not in html_orig
    assert "pb-block kind-source step" in html_orig
    assert "t-step" in html_orig


def test_helpjson_summary_skips_raw_nodes():
    p = nodes.paragraph("", "Computes the absolute value.")
    raw = nodes.raw("", '<div class="pb-block-preview"><svg></svg></div>', format="html")
    assert _summary([p, raw]) == "Computes the absolute value."
