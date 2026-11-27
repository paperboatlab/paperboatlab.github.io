#!/usr/bin/env python3
"""Build one Paperboat docs site: a docs folder of .rst files -> HTML and help.json.

    python3 docs/site/build.py SRC OUT [--name N] [--title T] [--url U] [--repo U]
                               [--catalog FILE | --engine paperboat-catalog [--package P]]
                               [--blocks DIR] [--loose]

SRC is the site's docs folder (the engine's docs/api, a toolkit's <toolkit>/docs, a program's
docs). With a catalog (a JSON file, or --engine to dump one for --package), a page per block is
generated into blocks/: its ports and params from the catalog, its prose from
<blocks dir>/<type>/doc.rst (the block's own folder), else SRC/blocks/<type>.rst. The generated
pages exist only in the build. Warnings are errors unless --loose.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from block_graphic import render_block_preview

HERE = Path(__file__).resolve().parent


def esc(text: str) -> str:
    """Catalog text as literal rst."""
    return re.sub(r"([\\`*_|])", r"\\\1", text or "")


def indent(text: str, by: str = "   ") -> str:
    return "\n".join(by + line if line.strip() else "" for line in text.splitlines())


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ".. list-table::\n   :header-rows: 1\n\n"
    for row in [head, *rows]:
        out += "".join(f"   {'*' if i == 0 else ' '} - {cell or '—'}\n" for i, cell in enumerate(row))
    return out


def port_rows(ports: list[dict]) -> list[list[str]]:
    return [[f"``{p['id']}``", esc(p.get("type", "signal")), esc(p.get("unit", "")),
             esc(", ".join(c["id"] for c in p.get("components", [])) or (f"× {p['dimension']}" if p.get("dimension") else ""))]
            for p in ports]


def param_row(p: dict) -> list[str]:
    default = p.get("default", "")
    if isinstance(default, str):
        default = f'"{default}"' if default else ""
    notes = ", ".join(f"``{o}``" for o in p.get("options", [])) if p.get("type") == "enum" else esc(p.get("unit", ""))
    return [f"``{p['id']}``", esc(p.get("type", "")), f"``{default}``" if default != "" else "", notes]


def block_page(b: dict, prose: str, connectors: dict | None = None) -> str:
    title = esc(b.get("label") or b["type"])
    facts = [f"``{b['type']}``"] + [esc(b["group"])] * bool(b.get("group"))
    if b.get("feedthrough") is False:
        facts.append("no feedthrough: a feedback loop may pass through it")
    if b.get("elementwise"):
        facts.append("element by element: vectors in, vectors out")
    out = f"{title}\n{'=' * len(title)}\n\n{esc(b.get('description', ''))}\n\n{' · '.join(facts)}\n\n"
    preview = render_block_preview(b, connectors)
    out += f".. raw:: html\n\n{indent(preview)}\n\n"
    if prose.strip():
        out += f".. container:: pb-prose\n\n{indent(prose)}\n\n"
    head = ["Port", "Type", "Unit", "Components"]
    for name, ports, dynamic in (("Inputs", b.get("inputs", []), b.get("inputs_from") or b.get("ports_from")),
                                 ("Outputs", b.get("outputs", []), b.get("outputs_from"))):
        if dynamic:
            out += f"{name}\n{'-' * len(name)}\n\nOne per name in ``{dynamic}``.\n\n"
        elif ports:
            out += f"{name}\n{'-' * len(name)}\n\n{table(head, port_rows(ports))}\n"
    if b.get("params"):
        out += f"Parameters\n----------\n\n{table(['Param', 'Type', 'Default', 'Options or unit'], [param_row(p) for p in b['params']])}\n"
    return out


def write_blocks(src: Path, catalog: dict, blocks_dir: Path | None) -> None:
    blocks = [b for b in catalog.get("blocks", []) if not b.get("linked")]
    connectors = catalog.get("connectors")
    out = src / "blocks"
    out.mkdir(exist_ok=True)
    groups: dict[str, list[dict]] = {}
    for b in blocks:
        own = blocks_dir / b["type"].split("/")[-1] / "doc.rst" if blocks_dir else None
        fallback = out / f"{b['type']}.rst"
        prose = own.read_text() if own and own.exists() else fallback.read_text() if fallback.exists() else ""
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(block_page(b, prose, connectors))
        groups.setdefault(b.get("group") or "blocks", []).append(b)
    index = "Blocks\n======\n\nEvery block of this toolkit, from its catalog.\n\n"
    for group, members in groups.items():
        if len(groups) > 1:
            index += f"{esc(group)}\n{'-' * len(esc(group))}\n\n"
        rows = [[f":doc:`{esc(b.get('label') or b['type'])} <{b['type']}>`", f"``{b['type']}``", esc(b.get("description", ""))] for b in members]
        index += table(["Block", "Type", "What it does"], rows) + "\n"
    index += ".. toctree::\n   :hidden:\n\n" + "".join(f"   {b['type']}\n" for b in blocks)
    (out / "index.rst").write_text(index)


def dump_catalog(engine: str, package: str, work: Path) -> dict:
    descriptor = work / "descriptor.toml"
    descriptor.write_text(f'domain = "docs"\nimport = ["{package}"]\n')
    return json.loads(subprocess.run([engine, str(descriptor)], check=True, capture_output=True, text=True).stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--name", default="paperboat", help="the site's path on the org site (toolkits/control)")
    ap.add_argument("--title")
    ap.add_argument("--url", help="where it is served (default: the org site + name)")
    ap.add_argument("--repo", help="its repository, for the top bar")
    ap.add_argument("--version", default="")
    ap.add_argument("--versions-json", default="", help="JSON list of {version, url} entries for the version switcher")
    ap.add_argument("--catalog", type=Path)
    ap.add_argument("--engine", help="a paperboat-catalog binary, to dump the catalog of --package")
    ap.add_argument("--package")
    ap.add_argument("--blocks", type=Path, help="the toolkit folder, holding <block>/doc.rst")
    ap.add_argument("--loose", action="store_true", help="warnings are not errors")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        shutil.copytree(args.src, src, ignore=shutil.ignore_patterns("_build"))
        catalog = None
        if args.catalog:
            catalog = json.loads(args.catalog.read_text())
        elif args.engine:
            catalog = dump_catalog(args.engine, args.package or args.name.split("/")[-1], Path(tmp))
        if catalog:
            write_blocks(src, catalog, args.blocks)
        env = {**os.environ, "PB_SITE": args.name, "PB_TITLE": args.title or args.name.split("/")[-1],
               "PB_VERSION": args.version, "PB_SITE_DIR": str(HERE)}
        if args.versions_json:
            vj = Path(args.versions_json)
            env["PB_VERSIONS_JSON"] = vj.read_text() if vj.exists() else args.versions_json
        if args.url:
            env["PB_SITE_URL"] = args.url
        if args.repo:
            env["PB_REPO_URL"] = args.repo
        conf = [] if (src / "conf.py").exists() else ["-c", str(HERE)]
        cmd = [sys.executable, "-m", "sphinx", "-E", "-a", "-q", *([] if args.loose else ["-W"]), *conf, "-b", "html", str(src), str(args.out)]
        return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
