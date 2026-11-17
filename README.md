# paperboatlab.github.io

The documentation hub for [Paperboat](https://github.com/paperboatlab/paperboat),
<https://paperboatlab.github.io/>: every repository's documentation built into one site with one
theme, one version switcher, and one search index. No individual repository turns GitHub Pages on
for itself, as a project site would shadow its path here.

| Path | Source |
| --- | --- |
| `/` | the hub (`hub.html`), `sites.json`, and `versions.json` |
| `/<site>/` | each site's default version (`release` branch > newest `v*` tag > `dev`) |
| `/<site>/<version>/` | versioned builds tracked from git (`release`, `v*` tags, `dev`) |
| `/paperboat/` | `paperboat/docs/api/` |
| `/toolkits/<package>/` | `paperboat/engine/toolkit/src/<package>/docs/` (built-in toolkits) |
| `/toolkits/<name>/` | `engine/toolkit/<name>/docs/` in each optional toolkit's repository |
| `/apps/<name>/` | `docs/` in each program's repository |

`build.py` reads `toolkits.toml` and `apps.toml` from `paperboat`, clones the listed repositories,
discovers tracked versions directly from git refs (`release` branch if present, SemVer `v*` tags,
and `dev`), and builds each version with `paperboat/docs/site/build.py` (producing HTML and the
`help.json` bundle used by each app's Help window).

## Build

With the repositories cloned under `work/`:

```sh
python3 build.py --work work --fetch
python3 build.py --work work --out _site --engine ../paperboat/engine/build/tools/paperboat-catalog
python3 -m http.server -d _site
```

Run the unit tests:

```sh
python3 -m unittest test_build.py
```

## CI and releasing

[![pages](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml/badge.svg?branch=release)](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml?query=branch%3Arelease)

- Changes to the hub/builder land on `dev` (verified on PRs and pushes without publishing).
- Releasing the docs site happens on the `release` branch (merge `dev` into `release`), nightly,
  manually via `workflow_dispatch`, or on `docs` / `release` `repository_dispatch` events.
