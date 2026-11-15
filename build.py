#!/usr/bin/env python3
"""Build the org's docs site: every repository's docs, one site each, under one domain.

    python3 build.py --work WORK --fetch                 # clone what the manifests name
    python3 build.py --work WORK --out OUT --engine paperboat-catalog [--previous PREV]

WORK holds a paperboat checkout (WORK/paperboat); every other repository is cloned next to it
from the paperboat manifests (toolkits.toml, apps.toml), so this repository keeps no list of its
own. Each site is built by paperboat's docs/site/build.py (HTML and help.json) into
OUT/<site>/. A site that fails keeps its build from PREV (the last deploy), marked stale, so one
broken repository never takes the others down. OUT/sites.json lists them all; OUT/index.html is
the hub.
"""

import argparse
import datetime
import html
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORG = "https://github.com/paperboatlab/"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def checkout(work: Path, name: str, url: str) -> Path:
    path = work / name
    if not path.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, str(path)], check=True)
    return path


def sites(work: Path) -> list[dict]:
    """Every site, from the manifests: the engine, its built-in toolkits, the optional toolkits,
    and every app whose repository has a docs/ folder (the rest get a card linking the repo)."""
    pb = work / "paperboat"
    out = [{"site": "paperboat", "title": "Paperboat", "kind": "engine", "repo": ORG + "paperboat",
            "checkout": pb, "src": pb / "docs/api"}]
    for docs in sorted((pb / "engine/toolkit/src").glob("*/docs")):
        name = docs.parent.name
        out.append({"site": f"toolkits/{name}", "title": name, "kind": "toolkit", "builtin": True,
                    "repo": ORG + "paperboat", "checkout": pb, "src": docs, "package": name, "blocks": docs.parent})
    for t in tomllib.loads((pb / "toolkits.toml").read_text())["toolkits"]:
        repo = checkout(work, f"toolkit-{t['name']}", t["repo"])
        folder = repo / "engine/toolkit" / t["name"]
        out.append({"site": f"toolkits/{t['name']}", "title": t["name"], "kind": "toolkit", "repo": t["repo"].removesuffix(".git"),
                    "description": t.get("description", ""), "requires": t.get("requires", []), "checkout": repo,
                    "src": folder / "docs", "package": t["name"], "blocks": folder / "src" / t["name"]})
    for a in tomllib.loads((pb / "apps.toml").read_text())["apps"]:
        repo = checkout(work, a["name"], a["repo"])
        kind = "program" if a.get("kind") == "program" else "library"
        entry = {"site": f"apps/{a['name']}", "title": a["name"], "kind": kind, "repo": a["repo"].removesuffix(".git"),
                 "description": a.get("description", ""), "checkout": repo, "port": a.get("port")}
        if (repo / "docs/index.rst").exists():
            entry["src"] = repo / "docs"
        out.append(entry)
    return out


def build_site(s: dict, out: Path, builder: Path, engine: str) -> tuple[bool, str]:
    cmd = [sys.executable, str(builder), str(s["src"]), str(out), "--name", s["site"], "--repo", s["repo"]]
    if s["kind"] == "program":
        cmd += ["--title", s["title"]]
    if s.get("package"):
        cmd += ["--engine", engine, "--package", s["package"], "--blocks", str(s["blocks"])]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0, (res.stdout + res.stderr)[-4000:]


def card(s: dict) -> str:
    esc = html.escape
    href = f"{s['site']}/" if s.get("status") in ("ok", "stale") else s["repo"]
    status = {"ok": "", "stale": '<span class="warn">build failed · last good shown</span>',
              "failed": '<span class="fail">build failed</span>'}.get(s.get("status", ""), '<span>README</span>')
    meta = [f"<b>{esc(s['commit'])}</b>"] if s.get("commit") else []
    if s.get("blocks_count"):
        meta.append(f"<b>{s['blocks_count']}</b> blocks")
    if s.get("builtin"):
        meta.append("built in")
    for r in s.get("requires", []):
        meta.append(f"needs {esc(r)}")
    if s.get("port"):
        meta.append(f"port {s['port']}")
    return (f'<a class="card" href="{esc(href)}"><div class="h"><span class="n">{esc(s["title"])}</span></div>'
            f'<p>{esc(s.get("description", ""))}</p><div class="meta">{" ".join(f"<span>{m}</span>" for m in meta)}{status}</div></a>')


def hub(all_sites: list[dict], built: str) -> str:
    groups = [("engine", "the framework: manuals, SDKs, protocol", lambda s: s["kind"] == "engine"),
              ("toolkits", "blocks by package; the optional ones install per user", lambda s: s["kind"] == "toolkit"),
              ("programs", "paperboat start <name>", lambda s: s["kind"] == "program"),
              ("libraries", "what the programs build on", lambda s: s["kind"] == "library")]
    body = ""
    for name, note, pick in groups:
        members = [s for s in all_sites if pick(s)]
        body += (f'<section><div class="sect-h"><h2>{name}</h2><span>{len(members)} · {html.escape(note)}</span><hr></div>'
                 f'<div class="grid">{"".join(card(s) for s in members)}</div></section>')
    template = (HERE / "hub.html").read_text()
    return template.replace("{{sections}}", body).replace("{{built}}", built)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--engine", help="paperboat-catalog, built with every optional toolkit")
    ap.add_argument("--fetch", action="store_true", help="only clone the repositories (to build the engine with the toolkits)")
    ap.add_argument("--previous", type=Path, help="the last deploy, for the sites that fail now")
    args = ap.parse_args()

    all_sites = sites(args.work)
    if args.fetch:
        return 0
    if not (args.out and args.engine):
        ap.error("--out and --engine are needed to build")
    builder = args.work / "paperboat/docs/site/build.py"
    shutil.rmtree(args.out, ignore_errors=True)
    args.out.mkdir(parents=True)
    failed = 0
    for s in all_sites:
        s["commit"] = git(s["checkout"], "rev-parse", "--short", "HEAD")
        if "src" not in s:
            continue
        dest = args.out / s["site"]
        ok, log = build_site(s, dest, builder, args.engine)
        if ok:
            s["status"] = "ok"
        else:
            failed += 1
            print(f"::error title={s['site']} docs failed::{log}", file=sys.stderr)
            prev = args.previous / s["site"] if args.previous else None
            shutil.rmtree(dest, ignore_errors=True)
            if prev and (prev / "help.json").exists():
                shutil.copytree(prev, dest)
                s["status"] = "stale"
            else:
                s["status"] = "failed"
        if (dest / "help.json").exists():
            help = json.loads((dest / "help.json").read_text())
            s["help"] = f"{s['site']}/help.json"
            s["blocks_count"] = len(list((dest / "blocks").glob("**/*.html"))) - 1 if (dest / "blocks").exists() else 0
            intro = next((i for i in help["items"] if i["id"] == "index"), None)
            if not s.get("description") and intro:
                s["description"] = intro["summary"]
        print(f"{s['site']:32} {s.get('status', 'readme')}")

    built = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    keys = ("site", "title", "kind", "description", "repo", "commit", "status", "help", "builtin", "requires", "port", "blocks_count")
    (args.out / "sites.json").write_text(json.dumps([{k: s[k] for k in keys if s.get(k) not in (None, "", [])} for s in all_sites], indent=1))
    (args.out / "index.html").write_text(hub(all_sites, built))
    static = args.work / "paperboat/docs/_static"
    shutil.copytree(static / "fonts", args.out / "_hub/fonts")
    for f in ("fonts.css", "favicon.svg", "logo-light.svg", "logo-dark.svg"):
        shutil.copy(static / f, args.out / "_hub" / f)
    (args.out / ".nojekyll").touch()  # Sphinx's _static and _images folders
    print(f"{len(all_sites)} sites, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
