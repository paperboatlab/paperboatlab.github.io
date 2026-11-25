#!/usr/bin/env python3
"""Build the org's docs site: every repository's docs across tracked git versions, under one domain.

    python3 build.py --work WORK --fetch                 # clone/fetch what the manifests name
    python3 build.py --work WORK --out OUT --engine paperboat-catalog [--previous PREV]

WORK holds a paperboat checkout (WORK/paperboat); every other repository is cloned next to it
from the paperboat manifests (toolkits.toml, apps.toml), so this repository keeps no list of its
own. Versions for every repository are tracked directly from git refs (`release` branch if present,
`v*` release tags, and `dev`). Each site/version is built by paperboat's docs/site/build.py into
OUT/<site>/<version>/, and each site's default version (release > latest tag > dev) is also served
at OUT/<site>/ for backwards-compatible links and `@paperboat/shared` Help lookups.
"""

import argparse
import datetime
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORG = "https://github.com/paperboatlab/"
SITE_ORG_URL = "https://paperboatlab.org/"
SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).returncode == 0


def parse_semver(tag: str) -> tuple[int, int, int, int, tuple] | None:
    """Parse a `vX.Y.Z[-pre]` tag into a sortable key (stable sorts higher than prerelease)."""
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4)
    if not pre:
        return (major, minor, patch, 1, ())
    parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split("."))
    return (major, minor, patch, 0, parts)


def checkout(work: Path, name: str, url: str, fetch: bool = False) -> Path:
    path = work / name
    if not path.exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", url, str(path)], check=True)
    elif fetch and git_ok(path, "remote", "get-url", "origin"):
        subprocess.run(
            ["git", "-C", str(path), "fetch", "-q", "--tags", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"],
            check=False,
        )
    return path


def resolve_branch_ref(repo: Path, branch: str) -> str | None:
    for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
        if git_ok(repo, "rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


def discover_versions(repo: Path, *, include_prereleases: bool = False, max_tags: int = 0) -> list[dict]:
    """Discover tracked git versions for `repo`: `release` branch (if any), `v*` tags, and `dev`."""
    versions: list[dict] = []
    seen_versions: set[str] = set()

    release_ref = resolve_branch_ref(repo, "release")
    if release_ref:
        commit = git(repo, "rev-parse", "--short", release_ref)
        versions.append({
            "version": "release",
            "ref": release_ref,
            "commit": commit,
            "channel": "release",
            "immutable": False,
        })
        seen_versions.add("release")

    raw_tags = git(repo, "tag", "-l", "v*").splitlines()
    parsed = [(parse_semver(t), t) for t in raw_tags]
    valid_tags = [(key, tag) for key, tag in parsed if key is not None]
    valid_tags.sort(key=lambda item: item[0], reverse=True)

    stable_tags = [(key, tag) for key, tag in valid_tags if key[3] == 1]
    pre_tags = [(key, tag) for key, tag in valid_tags if key[3] == 0]

    selected_tags = valid_tags if include_prereleases else (stable_tags or pre_tags[:1])
    if max_tags > 0:
        selected_tags = selected_tags[:max_tags]

    for _, tag in selected_tags:
        if tag in seen_versions:
            continue
        commit = git(repo, "rev-parse", "--short", f"refs/tags/{tag}")
        versions.append({
            "version": tag,
            "ref": f"refs/tags/{tag}",
            "commit": commit,
            "channel": "release",
            "immutable": True,
        })
        seen_versions.add(tag)

    dev_ref = resolve_branch_ref(repo, "dev") or resolve_branch_ref(repo, "main") or "HEAD"
    if "dev" not in seen_versions and git_ok(repo, "rev-parse", "--verify", "--quiet", dev_ref):
        commit = git(repo, "rev-parse", "--short", dev_ref)
        versions.append({
            "version": "dev",
            "ref": dev_ref,
            "commit": commit,
            "channel": "dev",
            "immutable": False,
        })

    return versions


def default_version(versions: list[dict]) -> dict | None:
    """Default version for `/<site>/`: `release` branch > newest release tag > `dev`."""
    for v in versions:
        if v["channel"] == "release":
            return v
    return versions[0] if versions else None


def materialize_ref(repo: Path, ref: str, dest: Path) -> Path:
    """Export `ref` from `repo` into `dest` via `git archive` (safe across concurrent/dirty checkouts)."""
    if (dest / ".pb-ref").exists() and (dest / ".pb-ref").read_text().strip() == ref:
        return dest
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref], capture_output=True, check=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(dest, filter="data")
    (dest / ".pb-ref").write_text(ref)
    return dest


def safe_dir_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def sites(
    work: Path,
    *,
    fetch: bool = False,
    include_prereleases: bool = False,
    max_tags: int = 0,
) -> list[dict]:
    """Every site and its git-tracked versions, from the manifests in paperboat."""
    pb_repo = work / "paperboat"
    if fetch and git_ok(pb_repo, "remote", "get-url", "origin"):
        subprocess.run(
            ["git", "-C", str(pb_repo), "fetch", "-q", "--tags", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"],
            check=False,
        )

    pb_versions = discover_versions(pb_repo, include_prereleases=include_prereleases, max_tags=max_tags)
    trees_root = work / ".trees"

    # Extract each tracked paperboat ref once so manifests and built-in toolkits come from that exact version.
    pb_trees: dict[str, Path] = {}
    toolkit_defs: dict[str, dict] = {}
    app_defs: dict[str, dict] = {}
    for v in pb_versions:
        tree = materialize_ref(pb_repo, v["ref"], trees_root / "paperboat" / safe_dir_name(v["version"]))
        pb_trees[v["version"]] = tree
        if (tree / "toolkits.toml").exists():
            for t in tomllib.loads((tree / "toolkits.toml").read_text()).get("toolkits", []):
                toolkit_defs.setdefault(t["name"], t)
        if (tree / "apps.toml").exists():
            for a in tomllib.loads((tree / "apps.toml").read_text()).get("apps", []):
                app_defs.setdefault(a["name"], a)

    # The new platform's app registry (paperboatlab/paperboat; the manifests above are paperboat-legacy's).
    # ponytail: read at origin/HEAD only, not per platform version; version it when the platform tags releases.
    platform = checkout(work, "platform", ORG + "paperboat", fetch=fetch)
    for ref in ("refs/remotes/origin/HEAD", "HEAD"):
        if git_ok(platform, "cat-file", "-e", f"{ref}:apps.toml"):
            for a in tomllib.loads(git(platform, "show", f"{ref}:apps.toml")).get("apps", []):
                app_defs.setdefault(a["name"], {**a, "kind": "app"})
            break

    # Engine site
    pb_site_versions = []
    builtin_names: list[str] = []
    seen_builtins: set[str] = set()
    for v in pb_versions:
        tree = pb_trees[v["version"]]
        src = tree / "docs/api"
        pb_site_versions.append({
            **v,
            "tree": tree,
            "src": src if (src / "index.rst").exists() else None,
        })
        if (tree / "engine/toolkit/src").exists():
            for docs in sorted((tree / "engine/toolkit/src").glob("*/docs")):
                pkg = docs.parent.name
                if pkg not in seen_builtins:
                    seen_builtins.add(pkg)
                    builtin_names.append(pkg)

    out: list[dict] = [{
        "site": "paperboat",
        "title": "Paperboat",
        "kind": "engine",
        "repo": ORG + "paperboat",
        "versions": pb_site_versions,
    }]

    # Built-in toolkits (versioned with paperboat)
    for pkg in sorted(builtin_names):
        pkg_versions = []
        for v in pb_versions:
            tree = pb_trees[v["version"]]
            docs = tree / "engine/toolkit/src" / pkg / "docs"
            pkg_versions.append({
                **v,
                "tree": tree,
                "src": docs if (docs / "index.rst").exists() else None,
                "package": pkg,
                "blocks": docs.parent,
            })
        out.append({
            "site": f"toolkits/{pkg}",
            "title": pkg,
            "kind": "toolkit",
            "builtin": True,
            "repo": ORG + "paperboat",
            "versions": pkg_versions,
        })

    # Optional toolkits (each tracks its own git refs)
    for name, t in toolkit_defs.items():
        repo = checkout(work, f"toolkit-{name}", t["repo"], fetch=fetch)
        t_versions = discover_versions(repo, include_prereleases=include_prereleases, max_tags=max_tags)
        ver_entries = []
        for v in t_versions:
            tree = materialize_ref(repo, v["ref"], trees_root / f"toolkit-{name}" / safe_dir_name(v["version"]))
            folder = tree / "engine/toolkit" / name
            docs = folder / "docs"
            ver_entries.append({
                **v,
                "tree": tree,
                "src": docs if (docs / "index.rst").exists() else None,
                "package": name,
                "blocks": folder / "src" / name,
            })
        out.append({
            "site": f"toolkits/{name}",
            "title": name,
            "kind": "toolkit",
            "repo": t["repo"].removesuffix(".git"),
            "description": t.get("description", ""),
            "requires": t.get("requires", []),
            "versions": ver_entries,
        })

    # Apps and libraries (each tracks its own git refs)
    for name, a in app_defs.items():
        repo = checkout(work, name, a["repo"], fetch=fetch)
        kind = a.get("kind") if a.get("kind") in ("app", "squero") else "library"
        a_versions = discover_versions(repo, include_prereleases=include_prereleases, max_tags=max_tags)
        ver_entries = []
        for v in a_versions:
            tree = materialize_ref(repo, v["ref"], trees_root / name / safe_dir_name(v["version"]))
            docs = tree / "docs"
            ver_entries.append({
                **v,
                "tree": tree,
                "src": docs if (docs / "index.rst").exists() else None,
            })
        out.append({
            "site": f"apps/{name}",
            "title": a.get("label") or name,
            "kind": kind,
            "repo": a["repo"].removesuffix(".git"),
            "description": a.get("description", ""),
            "port": a.get("port"),
            "versions": ver_entries,
        })

    return out


def pick_builder(ver_entry: dict, fallback_builder: Path) -> Path:
    tree = ver_entry.get("tree")
    cand = tree / "docs/site/build.py" if tree else None
    if cand and cand.exists() and "--versions-json" in cand.read_text():
        return cand
    return fallback_builder


def build_site(
    site: dict,
    ver: dict,
    out: Path,
    builder: Path,
    engine: str,
    url: str,
    versions_json: str,
) -> tuple[bool, str]:
    cmd = [
        sys.executable, str(builder), str(ver["src"]), str(out),
        "--name", site["site"],
        "--repo", site["repo"],
        "--version", ver["version"],
        "--url", url,
        "--versions-json", versions_json,
    ]
    if site["kind"] == "squero":
        cmd += ["--title", site["title"]]
    if ver.get("package"):
        cmd += ["--engine", engine, "--package", ver["package"], "--blocks", str(ver["blocks"])]
    res = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PB_ORG_URL": SITE_ORG_URL})
    return res.returncode == 0, (res.stdout + res.stderr)[-4000:]


def pick_engine(version: str, default_engine: str, engines_dir: Path | None) -> str:
    if engines_dir:
        cand = engines_dir / safe_dir_name(version) / "paperboat-catalog"
        if cand.exists():
            return str(cand)
    return default_engine


REBRAND_APPS = ("simplicial", "articula", "julix", "malachite")  # their own accent and tile (the rebrand)


def card(s: dict) -> str:
    esc = html.escape
    app = s["site"].removeprefix("apps/")
    app = app if s["site"].startswith("apps/") and app in REBRAND_APPS else ""
    href = f"{s['site']}/" if s.get("status") in ("ok", "stale") else s["repo"]
    status = {
        "ok": "",
        "stale": '<span class="warn">build failed · last good shown</span>',
        "failed": '<span class="fail">build failed</span>',
    }.get(s.get("status", ""), "<span>README</span>")
    meta: list[str] = []
    if s.get("version"):
        meta.append(f"<b>{esc(s['version'])}</b>")
    if s.get("commit"):
        meta.append(f"<b>{esc(s['commit'])}</b>")
    if s.get("blocks_count"):
        meta.append(f"<b>{s['blocks_count']}</b> blocks")
    if s.get("builtin"):
        meta.append("built in")
    for r in s.get("requires", []):
        meta.append(f"needs {esc(r)}")
    if s.get("port"):
        meta.append(f"port {s['port']}")
    built_vers = [v for v in s.get("versions", []) if v.get("status") in ("ok", "stale")]
    vers_html = ""
    if built_vers:
        pills = "".join(
            f'<a class="vpill{" on" if v["version"] == s.get("version") else ""}" '
            f'data-channel="{esc(v["channel"])}" href="{esc(v["url"])}">{esc(v["version"])}</a>'
            for v in built_vers
        )
        vers_html = f'<div class="vers">{pills}</div>'
    return (
        f'<article class="card" data-channel="{esc(s.get("channel", "dev"))}"{f' data-app="{app}"' if app else ""}>'
        f'<a class="card-main" href="{esc(href)}"><div class="h">'
        f'{f'<img class="ic" src="_hub/tiles/{app}.png" alt="">' if app else ""}'
        f'<span class="n">{esc(s["title"])}</span></div>'
        f'<p>{esc(s.get("description", ""))}</p></a>'
        f'{vers_html}'
        f'<div class="meta">{" ".join(f"<span>{m}</span>" for m in meta)}{status}</div>'
        f'</article>'
    )


def hub(all_sites: list[dict], built: str) -> str:
    groups = [
        ("Apps", "paperboat app open <name>", lambda s: s["kind"] == "app"),
        ("Platform", "manuals, SDKs, protocol", lambda s: s["kind"] == "engine"),
        ("Toolkits", "Simplicial's blocks by package", lambda s: s["kind"] == "toolkit"),
        ("Libraries", "what the apps build on", lambda s: s["kind"] == "library"),
        ("Squero (legacy)", "the apps before the rebrand", lambda s: s["kind"] == "squero"),
    ]
    body = ""
    for name, note, pick in groups:
        members = [s for s in all_sites if pick(s)]
        body += (
            f'<section><div class="sect-h"><h2>{name}</h2><span>{len(members)} · {html.escape(note)}</span><hr></div>'
            f'<div class="grid">{"".join(card(s) for s in members)}</div></section>'
        )
    template = (HERE / "hub.html").read_text()
    return template.replace("{{sections}}", body).replace("{{built}}", built)


def _prev_entry(prev_sites: dict, site_name: str, version: str) -> dict | None:
    site = prev_sites.get(site_name)
    if not site:
        return None
    for v in site.get("versions", []):
        if v.get("version") == version:
            return v
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--engine", help="paperboat-catalog, built with every optional toolkit")
    ap.add_argument("--engines-dir", type=Path, help="optional directory of per-version <ver>/paperboat-catalog binaries")
    ap.add_argument("--fetch", action="store_true", help="clone/fetch repositories and tracked git refs, then exit")
    ap.add_argument("--previous", type=Path, help="the last deploy, for failed sites and cached immutable tags")
    ap.add_argument("--org-url", default=SITE_ORG_URL, help="base URL where the site is served")
    ap.add_argument("--include-prereleases", action="store_true", help="include v*-alpha/rc tags even when stable tags exist")
    ap.add_argument("--max-tags", type=int, default=0, help="maximum release tags per repository (0 = all)")
    ap.add_argument("--reuse-tags", action="store_true", help="reuse immutable tag builds from --previous when commit and versions match")
    args = ap.parse_args()

    org_url = args.org_url if args.org_url.endswith("/") else args.org_url + "/"
    all_sites = sites(
        args.work,
        fetch=args.fetch,
        include_prereleases=args.include_prereleases,
        max_tags=args.max_tags,
    )
    if args.fetch:
        return 0
    if not (args.out and args.engine):
        ap.error("--out and --engine are needed to build")

    pb_repo = args.work / "paperboat"
    pb_versions = discover_versions(pb_repo, include_prereleases=args.include_prereleases, max_tags=args.max_tags)
    pb_dev = next((v for v in pb_versions if v["version"] == "dev"), None) or default_version(pb_versions)
    fallback_tree = (
        materialize_ref(pb_repo, pb_dev["ref"], args.work / ".trees/paperboat" / safe_dir_name(pb_dev["version"]))
        if pb_dev else pb_repo
    )
    fallback_builder = pb_repo / "docs/site/build.py"
    if not fallback_builder.exists() or "--versions-json" not in fallback_builder.read_text():
        fallback_builder = fallback_tree / "docs/site/build.py"

    prev_sites: dict[str, dict] = {}
    if args.previous and (args.previous / "sites.json").exists():
        for entry in json.loads((args.previous / "sites.json").read_text()):
            prev_sites[entry["site"]] = entry

    shutil.rmtree(args.out, ignore_errors=True)
    args.out.mkdir(parents=True)
    failed = 0

    for s in all_sites:
        versions = s["versions"]
        has_docs = [v for v in versions if v.get("src") is not None]
        # Build version switcher items only for versions that have docs.
        switcher_items = [
            {"version": v["version"], "url": f"{org_url}{s['site']}/{v['version']}/"}
            for v in has_docs
        ]
        versions_json = json.dumps(switcher_items) if switcher_items else ""

        built_versions: list[dict] = []
        for v in versions:
            ver_rel_url = f"{s['site']}/{v['version']}/"
            ver_out = args.out / s["site"] / v["version"]
            if v.get("src") is None:
                built_versions.append({
                    "version": v["version"],
                    "channel": v["channel"],
                    "ref": v["ref"],
                    "commit": v["commit"],
                    "url": s["repo"],
                })
                continue

            reused = False
            prev_ver = _prev_entry(prev_sites, s["site"], v["version"])
            prev_dir = args.previous / s["site"] / v["version"] if args.previous else None
            if (
                args.reuse_tags
                and v.get("immutable")
                and prev_ver
                and prev_ver.get("status") == "ok"
                and prev_ver.get("commit") == v["commit"]
                and prev_dir
                and (prev_dir / "help.json").exists()
                and prev_sites.get(s["site"], {}).get("versions")
                and [pv["version"] for pv in prev_sites[s["site"]]["versions"] if pv.get("help")] == [x["version"] for x in switcher_items]
            ):
                shutil.copytree(prev_dir, ver_out)
                status = "ok"
                reused = True
            else:
                builder = pick_builder(v, fallback_builder)
                engine_bin = pick_engine(v["version"], args.engine, args.engines_dir)
                ok, log = build_site(s, v, ver_out, builder, engine_bin, f"{org_url}{ver_rel_url}", versions_json)
                if ok:
                    status = "ok"
                else:
                    failed += 1
                    print(f"::error title={s['site']}@{v['version']} docs failed::{log}", file=sys.stderr)
                    shutil.rmtree(ver_out, ignore_errors=True)
                    if prev_dir and (prev_dir / "help.json").exists():
                        shutil.copytree(prev_dir, ver_out)
                        status = "stale"
                    else:
                        status = "failed"

            ver_record: dict = {
                "version": v["version"],
                "channel": v["channel"],
                "ref": v["ref"],
                "commit": v["commit"],
                "status": status,
                "url": ver_rel_url,
            }
            if (ver_out / "help.json").exists():
                help_data = json.loads((ver_out / "help.json").read_text())
                ver_record["help"] = f"{ver_rel_url}help.json"
                ver_record["blocks_count"] = len(list((ver_out / "blocks").glob("**/*.html"))) - 1 if (ver_out / "blocks").exists() else 0
                intro = next((i for i in help_data["items"] if i["id"] == "index"), None)
                if not s.get("description") and intro:
                    s["description"] = intro["summary"]
            built_versions.append(ver_record)
            tag = "cached" if reused else status
            print(f"{s['site']}@{v['version']:20} {tag}")

        # Pick the default version to expose at `/<site>/` (release > latest tag > dev), preferring one with docs.
        doc_built = [v for v in built_versions if v.get("status") in ("ok", "stale")]
        doc_raw_by_ver = {v["version"]: v for v in versions}
        chosen = default_version(doc_built) or default_version(built_versions)
        if chosen:
            s["version"] = chosen["version"]
            s["channel"] = chosen["channel"]
            s["commit"] = chosen["commit"]
            raw_chosen = doc_raw_by_ver[chosen["version"]]
            if raw_chosen.get("src") is not None:
                root_dest = args.out / s["site"]
                builder = pick_builder(raw_chosen, fallback_builder)
                engine_bin = pick_engine(chosen["version"], args.engine, args.engines_dir)
                with tempfile.TemporaryDirectory() as tmp_root:
                    tmp_out = Path(tmp_root) / "site"
                    ok, log = build_site(
                        s, raw_chosen, tmp_out, builder, engine_bin,
                        f"{org_url}{s['site']}/", versions_json,
                    )
                    if ok:
                        shutil.copytree(tmp_out, root_dest, dirs_exist_ok=True)
                        s["status"] = "ok"
                    else:
                        failed += 1
                        print(f"::error title={s['site']} (default {chosen['version']}) docs failed::{log}", file=sys.stderr)
                        prev_root = args.previous / s["site"] if args.previous else None
                        if prev_root and (prev_root / "help.json").exists():
                            root_dest.mkdir(parents=True, exist_ok=True)
                            for item in prev_root.iterdir():
                                if item.name not in {bv["version"] for bv in built_versions}:
                                    dst = root_dest / item.name
                                    if item.is_dir():
                                        shutil.copytree(item, dst, dirs_exist_ok=True)
                                    else:
                                        shutil.copy2(item, dst)
                            s["status"] = "stale"
                        else:
                            s["status"] = "failed"
                if (root_dest / "help.json").exists():
                    s["help"] = f"{s['site']}/help.json"
                    s["blocks_count"] = len(list((root_dest / "blocks").glob("**/*.html"))) - 1 if (root_dest / "blocks").exists() else 0
            else:
                print(f"{s['site']:32} readme")
        s["versions"] = built_versions

    built = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    keys = ("site", "title", "kind", "description", "repo", "version", "channel", "commit", "status", "help", "builtin", "requires", "port", "blocks_count", "versions")
    serialized_sites = [{k: s[k] for k in keys if s.get(k) not in (None, "", [])} for s in all_sites]
    (args.out / "sites.json").write_text(json.dumps(serialized_sites, indent=1))
    (args.out / "versions.json").write_text(json.dumps({
        "built": built,
        "sites": [
            {
                "site": s["site"],
                "default": s.get("version"),
                "versions": [
                    {k: v[k] for k in ("version", "channel", "ref", "commit", "status", "url", "help") if v.get(k) is not None}
                    for v in s.get("versions", [])
                ],
            }
            for s in all_sites
        ],
    }, indent=1))
    shutil.copy(HERE / "landing.html", args.out / "index.html")   # the landing; built in agent-docs/rebrand/apps/site
    (args.out / "docs").mkdir(exist_ok=True)
    (args.out / "docs/index.html").write_text(hub(all_sites, built))

    static_root = fallback_tree / "docs/_static"
    if not static_root.exists():
        static_root = pb_repo / "docs/_static"
    shutil.copytree(static_root / "fonts", args.out / "_hub/fonts")
    shutil.copy(static_root / "tokens.css", args.out / "_hub/tokens.css")   # generated from paperboat-ui
    if (static_root / "tiles").exists():
        shutil.copytree(static_root / "tiles", args.out / "_hub/tiles")
    (args.out / ".nojekyll").touch()  # Sphinx's _static and _images folders
    print(f"{len(all_sites)} sites, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
