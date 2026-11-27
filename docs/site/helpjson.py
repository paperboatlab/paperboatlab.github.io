"""Sphinx extension: writes help.json next to the HTML, the search bundle the apps' Help window loads.

One item per page (its text before the first section) and one per section, each with its HTML,
links made absolute so they open the site. A block page (blocks/<type>) is one item marked with
its `block`: the hub's search finds it, the apps skip it (they draw a block's page from the live
catalog) and take only its prose from `blocks`.

    {"site", "title", "url", "items": [{"id", "title", "page", "url", "summary", "html", "block"?}],
     "blocks": {"<type>": "<html>"}}
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from docutils import nodes
from docutils.utils import new_document

HEADERLINK = re.compile(r'<a class="headerlink"[^>]*>.*?</a>', re.S)
LINK = re.compile(r'(href|src)="([^"]*)"')
HEADING = re.compile(r"<(/?)h([1-6])")
# The page's doctree has been through the writer, so a note already holds its title paragraph.
TWICE = re.compile(r'(<p class="admonition-title">[^<]*</p>)\s*\1')


def _html(app, children, url):
    # The builder's render_partial would run docutils' transforms again, which fail on the C++
    # domain's nodes; the doctree is resolved already, so translate it as it is.
    doc = new_document("<help>", app.builder._settings)
    doc.extend(child.deepcopy() for child in children)
    visitor = app.builder.create_translator(doc, app.builder)
    doc.walkabout(visitor)
    out = "".join(visitor.fragment)
    out = TWICE.sub(r"\1", HEADERLINK.sub("", out))
    # Headings start at h3 in Help (the window's page title is h2).
    out = HEADING.sub(lambda m: f"<{m[1]}h{min(6, int(m[2]) + 2)}", out)
    return LINK.sub(lambda m: f'{m[1]}="{urljoin(url, m[2])}"', out)


def _summary(children):
    # Its own text first; a section that is only subsections is summed up by them.
    # Skip raw HTML blocks (such as the block preview) so markup never leaks into summaries.
    own = [c for c in children if not isinstance(c, (nodes.section, nodes.raw))]
    text = " ".join(c.astext() for c in (own or [c for c in children if not isinstance(c, nodes.raw)]))
    text = " ".join(text.split())
    return text[:157] + "…" if len(text) > 160 else text


def _page(app, pagename, templatename, context, doctree):
    if doctree is None or app.builder.format != "html":
        return
    top = next(iter(doctree.findall(nodes.section)), None)
    if top is None:
        return
    base = app.config.html_baseurl
    url = urljoin(base, pagename + ".html")
    title = top[0].astext()
    items = app.env.pb_help["items"]
    if pagename.startswith("blocks/") and pagename != "blocks/index":
        # One item for the whole page, marked: the hub searches it, the apps skip it (they draw a
        # block's page from the live catalog) and take only its prose from `blocks`.
        block = pagename.removeprefix("blocks/")
        prose = next((n for n in doctree.findall(nodes.container) if "pb-prose" in n["classes"]), None)
        if prose is not None:
            app.env.pb_help["blocks"][block] = _html(app, prose.children, url)
        body = top.children[1:]
        items.append({"id": pagename, "title": title, "page": title, "url": url, "block": block,
                      "summary": _summary(body), "html": _html(app, body, url)})
        return
    intro = [c for c in top.children[1:] if not isinstance(c, nodes.section)]
    if intro:
        items.append({"id": pagename, "title": title, "page": title, "url": url,
                      "summary": _summary(intro), "html": _html(app, intro, url)})
    for sec in (c for c in top.children if isinstance(c, nodes.section)):
        anchor = sec["ids"][0] if sec["ids"] else ""
        body = sec.children[1:]
        items.append({"id": f"{pagename}#{anchor}", "title": sec[0].astext(), "page": title,
                      "url": f"{url}#{anchor}", "summary": _summary(body), "html": _html(app, body, url)})


def _start(app):
    app.env.pb_help = {"items": [], "blocks": {}}


def _reading_order(env, root):
    """Docnames as the toctrees read them, from the root."""
    seen, order = set(), []
    def walk(doc):
        if doc in seen:
            return
        seen.add(doc)
        order.append(doc)
        for child in env.toctree_includes.get(doc, []):
            walk(child)
    walk(root)
    return {doc: i for i, doc in enumerate(order)}


def _finish(app, exc):
    if exc or app.builder.format != "html":
        return
    rank = _reading_order(app.env, app.config.root_doc)
    # Pages in reading order (the index first), each page's sections in their own order.
    app.env.pb_help["items"].sort(key=lambda i: rank.get(i["id"].split("#")[0], len(rank)))
    help = {"site": app.config.pb_site, "title": app.config.project, "url": app.config.html_baseurl,
            **({"version": app.config.release} if app.config.release else {}),
            **app.env.pb_help}
    Path(app.outdir, "help.json").write_text(json.dumps(help, ensure_ascii=False))


def setup(app):
    app.add_config_value("pb_site", "", "html")
    app.connect("builder-inited", _start)
    app.connect("html-page-context", _page)
    app.connect("build-finished", _finish)
    return {"parallel_read_safe": True, "parallel_write_safe": False}
