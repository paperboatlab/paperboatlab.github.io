# The Sphinx settings every Paperboat docs site shares: the engine's (docs/api), each toolkit's
# (<toolkit>/docs) and each program's (<repo>/docs). build.py passes the site's own values in the
# environment. A docs folder with no conf.py is built with docs/site/conf.py (just this); one that
# needs more (the engine's top-bar menus) keeps a conf.py that imports this and adds them.
#
#   python3 docs/site/build.py <docs dir> <out dir> --name control --title "control toolkit"

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SITE = os.environ.get("PB_SITE", "paperboat")
ORG = os.environ.get("PB_ORG_URL", "https://paperboatlab.org/")

project = os.environ.get("PB_TITLE", SITE)

# The rebrand: an app's site takes its accent and tile (tokens.css picks the accent from data-app on <html>);
# the platform, the toolkits and anything else stay on the umbrella's slate and the paperboat tile.
APPS = {"simplicial": "Simplicial", "articula": "Articula", "julix": "Julix", "malachite": "Malachite"}
PB_APP = SITE.removeprefix("apps/") if SITE.removeprefix("apps/") in APPS else ""
TILE = f"_static/tiles/{PB_APP or 'paperboat'}.png"
# The landing's nav (agent-docs/rebrand/apps/site); a site with menus of its own puts them first.
SITE_NAV = [
    {"title": "Apps", "url": ORG + "#apps"},
    {"title": "Download", "url": "https://github.com/paperboatlab/paperboat/releases"},
    {"title": "Docs", "url": ORG + "docs/"},
]
author = "Paperboat"
release = os.environ.get("PB_VERSION", "")
version = release

extensions = ["helpjson"]  # help.json, the apps' Help bundle
pb_site = SITE
exclude_patterns = ["_build"]
templates_path = [str(HERE / "_templates")]

html_theme = "shibuya"
html_static_path = [str(HERE.parent / "_static")]
html_css_files = ["tokens.css", "brand.css", "blocks.css"]
html_title = project
html_baseurl = os.environ.get("PB_SITE_URL", ORG + SITE + "/")
html_favicon = str(HERE.parent / TILE)
html_show_sphinx = False
highlight_language = "none"
primary_domain = None

html_theme_options = {
    "color_mode": "auto",
    "light_logo": TILE,
    "dark_logo": TILE,
    "github_url": "https://github.com/paperboatlab",
    # Every site's top bar is the landing's, so the org reads as one site: Docs is the hub (/docs/).
    "nav_links": SITE_NAV,
}
html_context = {
    "pb_app": PB_APP,
    "pb_org": ORG,
    "pb_lockup_pre": "" if SITE == "paperboat" else "Paperboat",
    "pb_lockup_name": APPS.get(PB_APP) or ("Paperboat" if SITE == "paperboat" else project),
}

_versions_raw = os.environ.get("PB_VERSIONS_JSON", "").strip()
if _versions_raw:
    _parsed = json.loads(_versions_raw)
    _choices = [(v["version"], v["url"]) if isinstance(v, dict) else (v[0], v[1]) for v in _parsed]
    html_context |= {
        "versions": _choices,
        "current_version": release or (_choices[0][0] if _choices else ""),
    }
