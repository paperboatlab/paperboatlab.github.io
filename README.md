# paperboatlab.github.io

The org's docs site, <https://paperboatlab.github.io/>: every repository's docs, built into one site
with one theme.

| Path | Source |
| --- | --- |
| `/` | the hub (`hub.html`) and `sites.json`, generated from the sites below |
| `/paperboat/` | `paperboat/docs/api` |
| `/toolkits/<package>/` | `paperboat/engine/toolkit/src/<package>/docs` (built in) |
| `/toolkits/<name>/` | `engine/toolkit/<name>/docs` in each optional toolkit's repository |
| `/apps/<name>/` | `docs/` in each program's repository |

Nothing here lists the repositories: `build.py` reads paperboat's `toolkits.toml` and `apps.toml`,
clones what they name, and builds each site with paperboat's `docs/site/build.py` (HTML, and the
`help.json` that the apps' Help window and the hub's search read). A toolkit's block pages are
generated from its catalog, dumped by an engine built with every optional toolkit. A site whose
build fails keeps its last good build and shows as stale on the hub. An app with no `docs/` gets a
card that links its repository.

`.github/workflows/pages.yml` runs nightly, on a push here, by hand, and on a `docs`
`repository_dispatch` (paperboat's `docs.yml` sends one after a docs change lands on `dev`).

Build it locally, with the repositories cloned (or linked) under `work/`:

```sh
python3 build.py --work work --fetch
python3 build.py --work work --out _site --engine ../paperboat/engine/build/tools/paperboat-catalog
python3 -m http.server -d _site
```

No repository turns GitHub Pages on for itself: a project site would shadow this one's path.
