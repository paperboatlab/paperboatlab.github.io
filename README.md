# paperboatlab.github.io

The documentation hub for [Paperboat](https://github.com/paperboatlab/paperboat),
<https://paperboatlab.github.io/>: every repository's documentation built into one site with one
theme and one search index. No individual repository turns GitHub Pages on for itself, as a project
site would shadow its path here.

| Path | Source |
| --- | --- |
| `/` | the hub (`hub.html`) and `sites.json`, generated from the sites below |
| `/paperboat/` | `paperboat/docs/api/` |
| `/toolkits/<package>/` | `paperboat/engine/toolkit/src/<package>/docs/` (built-in toolkits) |
| `/toolkits/<name>/` | `engine/toolkit/<name>/docs/` in each optional toolkit's repository |
| `/apps/<name>/` | `docs/` in each program's repository |

`build.py` reads `toolkits.toml` and `apps.toml` from `paperboat`, clones the listed repositories,
and builds each site with `paperboat/docs/site/build.py` (producing HTML and the `help.json` bundle
used by each app's Help window).

## Build

With the repositories cloned under `work/`:

```sh
python3 build.py --work work --fetch
python3 build.py --work work --out _site --engine ../paperboat/engine/build/tools/paperboat-catalog
python3 -m http.server -d _site
```

## CI

[![pages](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml/badge.svg?branch=dev)](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml?query=branch%3Adev) rebuilds and deploys the site nightly, on pushes to `dev`, and on `docs` `repository_dispatch` events.
