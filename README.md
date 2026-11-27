# paperboatlab.github.io

The documentation hub for [Paperboat](https://github.com/paperboatlab/paperboat),
<https://paperboatlab.org/>: the landing page, and every repository's documentation built into one site with one
theme, one version switcher, and one search index. No individual repository turns GitHub Pages on
for itself, as a project site would shadow its path here.

| Path | Source |
| --- | --- |
| `/` | the landing (`landing.html`, built by `agent-docs/rebrand/apps/site/build.py`: copy its `index.html` here, never edit it here), `sites.json`, and `versions.json` |
| `/docs/` | the docs hub (`hub.html`) |
| `/<site>/` | each site's default version (`release` branch > newest `v*` tag > `dev`) |
| `/<site>/<version>/` | versioned builds tracked from git (`release`, `v*` tags, `dev`) |
| `/toolkits/<package>/` | `simplicial/engine/toolkit/src/<package>/docs/` (built-in toolkits) |
| `/toolkits/<name>/` | `engine/toolkit/<name>/docs/` in each optional toolkit's repository |
| `/<app>/` | each app's page, what it is: `pages/app.html` filled from `pages/<app>.toml` (and `pages/<app>/`: the tile, screenshots). A `[[feature]]` with `shot = "<name>"` is shown large over `<name>-light.webp`/`-dark.webp`, a real 1440x900 window. A new app is a content file, never a new template; every app in the platform's `apps.toml` needs one |
| `/download/` | the Launcher and the newest release's packages, per target: `pages/download.html` in `pages/app.html`'s chrome; the buttons are filled in the browser from the GitHub API, so a release needs no rebuild |
| `/apps/<name>/` | `docs/` in each app's repository: the platform's `apps.toml` (`paperboatlab/paperboat`) |

`build.py` reads `toolkits.toml` from `simplicial` and `apps.toml` from `paperboat`, clones the listed
repositories, discovers tracked versions directly from git refs (`release` branch if present, SemVer
`v*` tags, and `dev`), and builds each version with this repository's `docs/site/build.py` and its theme
in `docs/_static/` (producing HTML and the `help.json` bundle used by each app's Help window). No
private repository is read: the -legacy repositories are private, and their manuals are no longer
published. `tokens.css` is generated from paperboat-ui (checked out beside this repository): run
`python3 docs/gen_tokens.py` when its tokens change (`--check` says whether they did).

## Build

With the repositories cloned under `work/`:

```sh
python3 build.py --work work --fetch
python3 build.py --work work --out _site --engine ../simplicial/engine/build/tools/paperboat-catalog
python3 -m http.server -d _site
```

Run the unit tests:

```sh
python3 -m unittest test_build.py      # the end-to-end build needs: pip install sphinx shibuya
```

## CI and releasing

[![pages](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml/badge.svg?branch=release)](https://github.com/paperboatlab/paperboatlab.github.io/actions/workflows/pages.yml?query=branch%3Arelease)

- Changes to the hub/builder land on `dev` (verified on PRs and pushes without publishing).
- Releasing the docs site happens on the `release` branch (merge `dev` into `release`), nightly,
  manually via `workflow_dispatch`, or on `docs` / `release` `repository_dispatch` events.
