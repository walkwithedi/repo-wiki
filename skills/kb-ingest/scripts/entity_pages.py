#!/usr/bin/env python3
"""Keep the related-files list of every entity page (references/entity-yaml.md) in step with the topic files.

  entity_pages.py ROOT --check       report the pages whose list is out of date; exit 1 when any is
  entity_pages.py ROOT --in-place    rewrite those pages in the library
  entity_pages.py ROOT --out OUT     with the files of an intake output folder laid over the library,
                                     write the pages that change into OUT/<entities_dir>/

A topic file belongs to an entity's list when a front-matter field links the entity ([[Name]]). The
list sits between the marks <!-- kb:related --> and <!-- /kb:related -->, one line per file, newest
document date first: a Markdown link (it opens on GitHub and in Obsidian), the date and the type field.
Nothing outside the marks changes. A page without the marks gets them right after the heading in front
of its Obsidian Bases block, else at the end under a related-files heading. package.py preview
--in-place runs the --out step itself, so every GitHub delivery carries the lists it changes.

stdout: what changed. stderr: log. Exit codes: 0 ok (with --check: all up to date); 1 --check found
out-of-date pages; 2 bad arguments.
"""
import argparse
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbconf  # noqa: E402

log = logging.getLogger("entity_pages")
REPO_FILES = {"README.md", "CLAUDE.md", "AGENTS.md"}
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
STAMP_RE = re.compile(r"\d{8}")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
BEGIN, END = "<!-- kb:related -->", "<!-- /kb:related -->"
TYPE_KEYS = ("type", "类型")
TEXT = {"zh": {"heading": "## 相关文件", "none": "暂无链接到本页的文件。", "sep": "｜"},
        "en": {"heading": "## Related files", "none": "No file links here yet.", "sep": " | "}}


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n")


def front_matter(text):
    """{key: raw value} of the front matter, or None when the file has none."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    out = {}
    for line in text[4:end].split("\n"):
        m = re.match(r"^([^\s:#][^:]*):\s*(.*)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def unquote(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def doc_date(fm):
    """The document date: the first date field that holds an ISO date, as YYYY-MM-DD, or ""."""
    for k, v in fm.items():
        if ("date" in k.casefold() or "日期" in k) and ISO_RE.match(unquote(v)):
            return unquote(v)[:10]
    return ""


def texts(cfg):
    return TEXT["zh"] if str(cfg.get("language", "zh")).startswith("zh") else TEXT["en"]


def summary_files(names, files):
    """Root files that are summary files (spec, status card, index and the like), by name or search key."""
    out = set()
    for key in kbconf.SUMMARY_KEYS:
        n = names[key]
        if n in files:
            out.add(n)
            continue
        k = names.get(f"{key}_key") or kbconf.search_key(n)
        out |= {f for f in files if f.endswith(".md") and k in f and not f.startswith(("_", "."))}
    return out


def is_topic(name, names):
    stem = name[:-3]
    return (name.endswith(".md") and not name.startswith(("_", ".", names["snapshot_prefix"])) and name not in REPO_FILES
            and not (names["old_suffix"] and names["old_suffix"] in stem
                     and STAMP_RE.search(stem.split(names["old_suffix"])[-1])))


def collect(root, names, overlay):
    """({entity: [(date, stem, type)]}, {page name: path}) for the library with overlay laid over it.

    overlay maps a relative path (a root file, or <entities_dir>/<page>.md) to the file that replaces it."""
    ent = names["entities_dir"]
    files = {f: os.path.join(root, f) for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))}
    files.update({r: p for r, p in overlay.items() if "/" not in r})
    ent_dir = os.path.join(root, ent)
    pages = {f[:-3]: os.path.join(ent_dir, f) for f in os.listdir(ent_dir)
             if f.endswith(".md")} if os.path.isdir(ent_dir) else {}
    pages.update({r.split("/", 1)[1][:-3]: p for r, p in overlay.items()
                  if r.startswith(ent + "/") and r.endswith(".md")})
    skip = summary_files(names, files)
    related = {n: [] for n in pages}
    for name in sorted(files):
        if name in skip or not is_topic(name, names):
            continue
        fm = front_matter(read(files[name]))
        if not fm:
            continue
        linked = {x.strip() for v in fm.values() for x in WIKI_RE.findall(v)}
        kind = next((unquote(fm[k]) for k in TYPE_KEYS if k in fm), "")
        for n in linked & set(related):
            related[n].append((doc_date(fm), name[:-3], kind))
    for rows in related.values():
        rows.sort(key=lambda r: r[1])
        rows.sort(key=lambda r: r[0], reverse=True)  # newest first; files without a date ("") last
    return related, pages


def block(rows, t):
    if not rows:
        return f"{BEGIN}\n{t['none']}\n{END}"
    lines = []
    for d, stem, kind in rows:
        cells = [f"[{stem}](<../{stem}.md>)"] + [x for x in (d, kind) if x]
        lines.append("- " + t["sep"].join(cells))
    return BEGIN + "\n" + "\n".join(lines) + "\n" + END


def render(text, rows, t):
    """The page text with its related-files list replaced or added."""
    new = block(rows, t)
    i, j = text.find(BEGIN), text.find(END)
    if i >= 0 and j > i:
        return text[:i] + new + text[j + len(END):]
    lines = text.split("\n")
    fence = next((k for k, x in enumerate(lines) if x.strip().startswith("```base")), None)
    if fence is not None:
        head = next((k for k in range(fence - 1, -1, -1) if lines[k].startswith("#")), None)
        at = head + 1 if head is not None else fence
        before, after = lines[:at], lines[at:]
        while before and not before[-1].strip():
            before.pop()
        while after and not after[0].strip():
            after.pop(0)
        return "\n".join(before + ["", new, ""] + after)
    return text.rstrip("\n") + f"\n\n{t['heading']}\n\n{new}\n"


def changes(root, cfg, overlay=None):
    """[(page name, page path, new text)] for every page whose text would change."""
    names, t = cfg["names"], texts(cfg)
    related, pages = collect(root, names, overlay or {})
    out = []
    for n in sorted(pages):
        old = read(pages[n])
        new = render(old, related[n], t)
        if new != old:
            out.append((n, pages[n], new))
        log.debug("%s: %d related files", n, len(related[n]))
    return out


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def refresh_into(root, cfg, overlay, out_dir):
    """Write the pages that change, with overlay laid over the library, into out_dir/<entities_dir>/.

    Returns [(relative path, written path)]."""
    ent = cfg["names"]["entities_dir"]
    done = []
    for n, _, text in changes(root, cfg, overlay):
        p = os.path.join(out_dir, ent, n + ".md")
        write(p, text)
        done.append((f"{ent}/{n}.md", p))
    log.info("related lists: %d page(s) changed", len(done))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", help="library root (a checkout of a GitHub library)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report only; exit 1 when a list is out of date")
    mode.add_argument("--in-place", action="store_true", help="rewrite the out-of-date pages in the library")
    mode.add_argument("--out", help="intake output folder: lay its files over the library, write changed pages into it")
    kbconf.add_log_args(ap)
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    try:
        cfg = kbconf.load_library(a.root)
    except kbconf.ConfigError as e:
        log.error("%s", e)
        sys.exit(2)
    root = os.path.dirname(cfg["_path"])
    ent = cfg["names"]["entities_dir"]
    if a.out:
        overlay = {}
        for dirpath, _, filenames in os.walk(a.out):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), a.out).replace(os.sep, "/")
                if rel.endswith(".md") and ("/" not in rel or rel.startswith(ent + "/")):
                    overlay[rel] = os.path.join(dirpath, fn)
        done = refresh_into(root, cfg, overlay, a.out)
        for rel, _ in done:
            print(f"  updated | {rel}")
        print(f"Result: {len(done)} entity page(s) written into {a.out}")
        return
    found = changes(root, cfg)
    for n, path, text in found:
        if a.in_place:
            write(path, text)
        print(f"  {'updated' if a.in_place else 'out of date'} | {ent}/{n}.md")
    print(f"Result: {len(found)} entity page(s) {'rewritten' if a.in_place else 'out of date'}")
    if a.check and found:
        sys.exit(1)


if __name__ == "__main__":
    main()
