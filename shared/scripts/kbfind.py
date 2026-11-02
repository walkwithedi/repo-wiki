#!/usr/bin/env python3
"""Find the passages of a local library that answer a question, so that only those are read.

  find ROOT KEYWORD [KEYWORD ...] [--file PART] [--in FOLDER] [--all]
      Searches the Markdown files directly in ROOT (or in its subfolder FOLDER, such as the entities
      or notes folder), skipping what the skills never use as a source: other subfolders, names
      starting with an underscore or the snapshot prefix, and old versions (old suffix plus a time
      stamp). Keywords match without regard to case; a block matches when it holds any keyword (all
      of them with --all). For each match it prints the smallest block holding it (a numbered or
      bulleted item, a table row with its header row, a paragraph, the front matter), the headings
      above it and its line numbers, so the rest of that section can be read by line number.
  ask ROOT --q "WORDING|WORDING" [--q ...] [--all] [--entities] [--max-files N] [--max-chars N]
      One search for a question, everything local: each --q is one keyword with up to three of its
      wordings; the spec's Table B (old and standard forms) and Table E (names and aliases) add the
      other forms of each. It prints the matching blocks of the status card and the file index first
      (up to 15 each), then the open items, change log and glossary, then the source files in the
      root (files the status card or index hits name first, then files with a keyword in their name (also when only
      the name holds it),
      then in their front matter, then by keywords and blocks matched; at most --max-files with 4
      blocks each, the rest by name, those with a keyword in their name listed apart, and a hint to
      narrow when many files hit), the entity pages of these keywords, the
      quick notes only when the library itself has nothing, and which hits still wait in the
      consolidation queue. The file index is matched line by line. A wording shaped like a library
      file name (<partition>_<topic>_<type>_<short title>) also searches its short title. A wording that starts or ends with a Latin letter or digit matches whole
      words only (PA is not found in Payments).
  history ROOT FILE [--words W ...] [--at HASH] [--limit N]
      Earlier versions of one knowledge file from git: the commits that changed it (git log --follow),
      the commits where each wording appeared or vanished (git log -S), and with --at the file as it
      was in that commit (blocks holding the words, else its headings).
  toc FILE
      The headings of FILE with the line range, size and number of list items or table rows of
      each section, for choosing sections by heading.

Read-only. Names come from the library's _kb.json (defaults when it has none). Output is capped
(--max-blocks, --max-per-file, --max-chars); the last line says what was left out.
stdout: the result. stderr: log. Exit code: 0 (also when nothing matched); 2 bad arguments.
"""
import argparse
import logging
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbconf  # noqa: E402

log = logging.getLogger("kbfind")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
ITEM_RE = re.compile(r"^ {0,3}(?:\d{1,4}[.)]|[-*+])\s+")
STAMP_RE = re.compile(r"\d{8}")
REPO_FILES = {"README.md", "CLAUDE.md", "AGENTS.md"}  # a GitHub library's repository files, not knowledge
BLOCK_CHARS = 700  # characters of one block printed; the rest is left to a read by line number
FILE_NAME_RE = re.compile(r"^\d{2}_[^_\s]+_[^_\s]+_(.+?)(?:\.md)?$")  # <partition>_<topic>_<type>_<short title>
MANY_FILES = 30  # source files with hits above which the output suggests narrowing the search


def ignored(name, names):
    """True for files the skills never use as a source (references/config.md, Ignored files)."""
    if not name.lower().endswith(".md") or name.startswith(("_", ".", names["snapshot_prefix"])):
        return True
    if name in REPO_FILES:
        return True
    stem = name[:-3]
    old = names["old_suffix"]
    return bool(old) and old in stem and bool(STAMP_RE.search(stem.split(old)[-1]))


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n").split("\n")


def is_table_row(line):
    s = line.strip()
    return s.startswith("|") or (s.count(" | ") >= 1 and not ITEM_RE.match(line))


def is_separator(line):
    return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", line))


def blocks(lines):
    """[(first line, last line, heading path, kind, table header line or None)], line numbers from 1.
    Headings start sections; within one, a block is a list item with its continuation lines, a table
    row, a paragraph or the front matter."""
    out, path, i, n = [], [], 0, len(lines)
    if n and lines[0].strip() == "---":
        end = next((j for j in range(1, n) if lines[j].strip() == "---"), None)
        if end is not None:
            out.append((1, end + 1, (), "front matter", None))
            i = end + 1
    header = None  # the header row of the table being read
    while i < n:
        line = lines[i]
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            path = [p for p in path if p[0] < level] + [(level, m.group(2))]
            out.append((i + 1, i + 1, tuple(t for _, t in path[:-1]), "heading", None))
            header, i = None, i + 1
            continue
        if not line.strip():
            header, i = None, i + 1
            continue
        heads = tuple(t for _, t in path)
        if is_table_row(line):
            if header is None:
                header = i + 1
                out.append((i + 1, i + 1, heads, "table header", None))
            elif not is_separator(line):
                out.append((i + 1, i + 1, heads, "table row", header))
            i += 1
            continue
        header = None
        start, kind = i, "item" if ITEM_RE.match(line) else "paragraph"
        i += 1
        while i < n and lines[i].strip() and not HEADING_RE.match(lines[i]) and not ITEM_RE.match(lines[i]) \
                and not is_table_row(lines[i]):
            i += 1
        out.append((start + 1, i, heads, kind, None))
    return out


def library_names(root):
    """The library's names; root may be the library or one of its folders."""
    for path in (root, os.path.dirname(os.path.normpath(root))):
        if os.path.isfile(os.path.join(path, kbconf.KB_JSON)):
            try:
                return kbconf.load_library(path)["names"]
            except (OSError, ValueError, kbconf.ConfigError) as e:
                log.warning("cannot read %s: %s; using the default names", kbconf.KB_JSON, e)
    return kbconf.resolve_names()


def shown(lines, b):
    text = "\n".join(lines[b[0] - 1:b[1]])
    if b[4]:
        text = lines[b[4] - 1] + "\n" + text
    if len(text) > BLOCK_CHARS:
        text = text[:BLOCK_CHARS].rstrip() + f" ... (block continues to line {b[1]})"
    return text


def find(root, keywords, part="", folder="", need_all=False, max_blocks=30, max_per_file=10, max_chars=12000):
    names = library_names(root)
    where = os.path.join(root, folder) if folder else root
    keys = [k.casefold() for k in keywords if k.strip()]
    files = sorted(f for f in os.listdir(where)
                   if os.path.isfile(os.path.join(where, f)) and not ignored(f, names)
                   and (not part or part.casefold() in f.casefold()))
    found = []
    for f in files:
        lines = read_lines(os.path.join(where, f))
        hits = []
        for b in blocks(lines):
            text = "\n".join(lines[b[0] - 1:b[1]]).casefold()
            got = [k for k in keys if k in text]
            if got and (not need_all or len(got) == len(keys)):
                hits.append(b)
        if hits:
            found.append((f, lines, hits))
    found.sort(key=lambda x: (-len(x[2]), x[0]))
    total = sum(len(h) for _, _, h in found)
    out = [f"keywords: {', '.join(keywords)}{' (all)' if need_all else ''} | folder: {folder or '(library root)'}"
           f" | files searched: {len(files)} | files with hits: {len(found)} | blocks: {total}"]
    used, printed, left_files = len(out[0]), 0, []
    for f, lines, hits in found:
        if printed >= max_blocks or used >= max_chars:
            left_files.append(f"{f} ({len(hits)})")
            continue
        size = sum(len(x) + 1 for x in lines)
        head = f"\n== {f} | {len(hits)} blocks | {size} characters, {len(lines)} lines"
        out.append(head)
        used += len(head)
        for k, b in enumerate(hits):
            if k >= max_per_file or printed >= max_blocks or used >= max_chars:
                out.append(f"({len(hits) - k} more blocks in this file; narrow the keywords or read by line number)")
                break
            where_in = " > ".join(b[2]) or "(no heading)"
            lines_txt = f"line {b[0]}" if b[0] == b[1] else f"lines {b[0]}-{b[1]}"
            text = f"-- {lines_txt} | {where_in}" + ("" if b[3] in ("item", "paragraph", "table row") else
                                                     f" | {b[3]}") + "\n" + shown(lines, b)
            out.append(text)
            used += len(text)
            printed += 1
    if left_files:
        out.append(f"\nnot shown (cap reached): {', '.join(left_files)}")
    if not found:
        out.append("no match")
    return "\n".join(out) + "\n"


# ---------- ask: one local search for a question ----------

SUMMARY_ORDER = ("status_card", "index", "open_items", "changelog", "glossary", "spec")


def wording_re(words):
    """Several wordings in one pattern, longest first, without regard to case; a wording that starts or ends
    with a Latin letter or digit must not touch another one there, CJK wordings match anywhere."""
    alts = []
    for w in sorted({w for w in words if w}, key=len, reverse=True):
        a = re.escape(w)
        if re.match(r"[A-Za-z0-9]", w):
            a = r"(?<![A-Za-z0-9])" + a
        if re.search(r"[A-Za-z0-9]$", w):
            a += r"(?![A-Za-z0-9])"
        alts.append(a)
    return re.compile("|".join(alts), re.I) if alts else None


def summary_files(root, names):
    """{key: file name} of the summary files found in the root: the configured name, else a name with its key."""
    files = [f for f in os.listdir(root) if f.endswith(".md") and os.path.isfile(os.path.join(root, f))]
    out = {}
    for key in SUMMARY_ORDER:
        if names[key] in files:
            out[key] = names[key]
            continue
        k = names.get(f"{key}_key") or kbconf.search_key(names[key])
        hit = sorted(f for f in files if k in f and not ignored(f, names))
        if hit:
            out[key] = hit[0]
    return out


def expand(groups, spec_text):
    """[(wordings, notes)] per keyword group: the user's wordings plus the Table B and Table E forms."""
    pairs = kbconf.term_pairs(spec_text) or [] if spec_text else []
    ents = kbconf.entity_list(spec_text) or [] if spec_text else []
    out = []
    for g in groups:
        words = [w.strip() for w in g.split("|") if w.strip()]
        notes = []
        low = {w.casefold() for w in words}
        for w in list(words):  # a file name: its short title also finds it after a partition or topic rename
            m = FILE_NAME_RE.match(w)
            if m and m.group(1).casefold() not in low:
                words.append(m.group(1))
                low.add(m.group(1).casefold())
                notes.append(f"{m.group(1)} (short title of a file name)")
        for orig, fixed in pairs:
            if orig.casefold() in low or (fixed and fixed.casefold() in low):
                for w, why in ((orig, "old form, Table B"), (fixed, "standard form, Table B")):
                    if w and w.casefold() not in low:
                        words.append(w)
                        low.add(w.casefold())
                        notes.append(f"{w} ({why})")
        for name, aliases in ents:
            forms = [name] + aliases
            if any(f.casefold() in low for f in forms):
                for f in forms:
                    if f.casefold() not in low and len(f) >= 2:
                        words.append(f)
                        low.add(f.casefold())
                        notes.append(f"{f} (Table E: {name})")
        out.append((words, notes))
    return out


def file_hits(path, rxs):
    """(lines, [(block, groups hit)]) for the blocks holding a wording of at least one group."""
    lines = read_lines(path)
    hits = []
    whole = "\n".join(lines)
    if not any(rx and rx.search(whole) for rx in rxs):  # most files: no wording at all, no need to split
        return lines, hits
    for b in blocks(lines):
        if b[3] == "heading" and b[0] == b[1]:
            text = lines[b[0] - 1]
        else:
            text = "\n".join(lines[b[0] - 1:b[1]])
        got = frozenset(k for k, rx in enumerate(rxs) if rx and rx.search(text))
        if got:
            hits.append((b, got))
    return lines, hits


def line_hits(path, rxs):
    """(lines, [(block, groups hit)]) with one block per matching line, for files of one entry per line
    (the file index) whose entries are not separated by blank lines."""
    lines = read_lines(path)
    hits = []
    for i, line in enumerate(lines):
        got = frozenset(k for k, rx in enumerate(rxs) if rx and rx.search(line))
        if got and line.strip():
            hits.append(((i + 1, i + 1, (), "line", None), got))
    return lines, hits


def block_text(lines, b):
    where_in = " > ".join(b[2]) or "(no heading)"
    lines_txt = f"line {b[0]}" if b[0] == b[1] else f"lines {b[0]}-{b[1]}"
    return f"-- {lines_txt} | {where_in}\n" + shown(lines, b)


class Out:
    """Output with a character budget; what does not fit is counted for the last line."""

    def __init__(self, budget):
        self.parts, self.used, self.budget, self.left = [], 0, budget, []

    def add(self, text, what=None):
        if self.used + len(text) > self.budget and what:
            self.left.append(what)
            return False
        self.parts.append(text)
        self.used += len(text) + 1
        return True


def ask(root, groups, need_all=False, entities=False, max_files=5, per_file=4, per_summary=8, budget=12000):
    names = library_names(root)
    summ = summary_files(root, names)
    spec_text = "\n".join(read_lines(os.path.join(root, summ["spec"]))) if "spec" in summ else ""
    expanded = expand(groups, spec_text)
    rxs = [wording_re(w) for w, _ in expanded]
    keep = (lambda got: len(got) == len(rxs)) if need_all else (lambda got: bool(got))
    out = Out(budget)
    out.add(f"library: {root}")
    for k, (words, notes) in enumerate(expanded, 1):
        out.add(f"keyword {k}: {' | '.join(words)}" + (f"  [added: {'; '.join(notes)}]" if notes else ""))
    out.add(f"match: {'every keyword in one block' if need_all else 'any keyword'}")

    named = set()  # file names that the status card or index hits mention: read those first
    any_hit = False
    for key in SUMMARY_ORDER:
        if key == "spec" or key not in summ:
            continue
        lines, hits = (line_hits if key == "index" else file_hits)(os.path.join(root, summ[key]), rxs)
        hits = [h for h in hits if keep(h[1])]
        cap = 15 if key in ("status_card", "index") else per_summary
        out.add(f"\n== {key}: {summ[key]} | {len(hits)} blocks | {len(lines)} lines")
        for k, (b, _) in enumerate(hits):
            if k >= cap:
                out.add(f"({len(hits) - k} more blocks; read by line number)")
                break
            text = block_text(lines, b)
            if not out.add(text, f"{summ[key]} line {b[0]}"):
                continue
            if key in ("status_card", "index"):
                named.update(re.findall(r"[^\s|\[\]()（）]+\.md", text))
        any_hit = any_hit or bool(hits)
    missing = [k for k in SUMMARY_ORDER if k not in summ]
    if missing:
        out.add("summary files not found: " + ", ".join(names[k] for k in missing))

    skip = set(summ.values())
    files = [f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f)) and not ignored(f, names)
             and f not in skip]
    found = []
    for f in files:
        lines, hits = file_hits(os.path.join(root, f), rxs)
        hits = [h for h in hits if keep(h[1])]
        name_got = frozenset(k for k, rx in enumerate(rxs) if rx and rx.search(f[:-3]))
        if not hits and name_got and keep(name_got):  # found by its name alone: show its opening block
            first = next((b for b in blocks(lines) if b[3] != "heading"), None) or (1, 1, (), "line", None)
            hits = [(first, name_got)]
        if hits:
            in_name = bool(name_got)
            in_meta = any(b[3] == "front matter" for b, _ in hits)
            found.append((f, lines, hits, in_name, in_meta))
    # files the summaries name, then a keyword in the file name, then in the front matter, then by the body
    found.sort(key=lambda x: (x[0] not in named, not x[3], not x[4],
                              -len({g for _, got in x[2] for g in got}), -len(x[2]), x[0]))
    log.debug("source files with hits: %d (in the name: %d, in the front matter: %d)",
              len(found), sum(x[3] for x in found), sum(x[4] for x in found))
    out.add(f"\n== source files | {len(files)} searched | {len(found)} with hits"
            + (f" (showing {min(len(found), max_files)})" if found else ""))
    for f, lines, hits, in_name, in_meta in found[:max_files]:
        tag = (" | named in the status card or index" if f in named else "") + (" | keyword in the file name"
               if in_name else " | keyword in the front matter" if in_meta else "")
        out.add(f"\n= {f} | {len(hits)} blocks | {len(lines)} lines{tag}")
        for k, (b, _) in enumerate(hits):
            if k >= per_file:
                out.add(f"({len(hits) - k} more blocks in this file)")
                break
            out.add(block_text(lines, b), f"{f} line {b[0]}")
    if len(found) > max_files:
        rest = found[max_files:]
        by_name = [x[0] for x in rest if x[3]]
        if by_name:
            out.add("also with a keyword in the file name: " + ", ".join(by_name[:MANY_FILES])
                    + (" ..." if len(by_name) > MANY_FILES else ""))
        others = [x for x in rest if not x[3]]
        if others:
            out.add("also with hits: " + ", ".join(f"{f} ({len(h)})" for f, _, h, _, _ in others[:15])
                    + (" ..." if len(others) > 15 else ""))
    if len(found) > MANY_FILES:
        out.add(f"many files hit ({len(found)}): add a keyword for the subject or occasion, or use --all to narrow")
    any_hit = any_hit or bool(found)

    ents = kbconf.entity_list(spec_text) or [] if spec_text else []
    ent_dir = os.path.join(root, names["entities_dir"])
    if os.path.isdir(ent_dir):
        pages = [f"{names['entities_dir']}/{n}.md" for n, al in ents
                 if os.path.isfile(os.path.join(ent_dir, f"{n}.md")) and any(rx and any(rx.fullmatch(x) for x in [n] + al) for rx in rxs)]
        if pages:
            out.add("entity pages for these keywords: " + ", ".join(pages))
        if entities:
            for f in sorted(os.listdir(ent_dir)):
                if not f.endswith(".md"):
                    continue
                lines, hits = file_hits(os.path.join(ent_dir, f), rxs)
                hits = [h for h in hits if keep(h[1])]
                if hits:
                    out.add(f"\n= {names['entities_dir']}/{f} | {len(hits)} blocks")
                    for b, _ in hits[:per_file]:
                        out.add(block_text(lines, b), f"{f} line {b[0]}")

    notes_dir = os.path.join(root, names["notes_dir"])
    if not any_hit and os.path.isdir(notes_dir):
        nfound = []
        for f in sorted(os.listdir(notes_dir)):
            if f.endswith(".md") and os.path.isfile(os.path.join(notes_dir, f)):
                lines, hits = file_hits(os.path.join(notes_dir, f), rxs)
                if [h for h in hits if keep(h[1])]:
                    nfound.append((f, lines))
        out.add(f"\n== quick notes (nothing in the library itself) | {len(nfound)} with hits")
        for f, lines in nfound[:max_files]:
            out.add(f"\n= {names['notes_dir']}/{f} (quick note, not yet filed)\n" + "\n".join(lines[:40]),
                    f"{names['notes_dir']}/{f}")

    queue = os.path.join(root, names["consolidation_queue"])
    if os.path.isfile(queue):
        qtext = "\n".join(read_lines(queue))
        waiting = [x[0] for x in found if x[0] in qtext]
        out.add(f"consolidation queue: present; files above still waiting: {', '.join(waiting) or 'none'}")
    if out.left:
        out.add(f"\nnot shown (output cap): {len(out.left)} blocks, from " + ", ".join(dict.fromkeys(
            x.split(' line ')[0] for x in out.left)))
    if not any_hit:
        out.add("\nno match in the library")
    return "\n".join(out.parts) + "\n"


# ---------- history: earlier versions from git ----------

def git_out(root, *args):
    p = subprocess.run(["git", "-C", root, "-c", "core.quotepath=false", *args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return p.stdout


def history(root, name, words=(), at="", limit=20):
    names = library_names(root)
    if ignored(os.path.basename(name), names) or "/" in name.strip("/") and not name.startswith(names["entities_dir"] + "/"):
        return f"not a knowledge file of this library: {name}\n"
    out = []
    if at:
        text = git_out(root, "show", f"{at}:{name}")
        lines = text.replace("\r\n", "\n").split("\n")
        date = git_out(root, "log", "-1", "--format=%h %ad", "--date=short", at).strip()
        out.append(f"{name} as of {date} (superseded version unless it is the current one) | {len(lines)} lines")
        rx = wording_re(words)
        if rx:
            hits = [b for b in blocks(lines) if rx.search("\n".join(lines[b[0] - 1:b[1]]))]
            out.append(f"blocks with {' | '.join(words)}: {len(hits)}")
            out += [block_text(lines, b) for b in hits[:15]]
        else:
            out.append("(no words given: the headings)")
            out += [f"  line {i}: {ln}" for i, ln in enumerate(lines, 1) if HEADING_RE.match(ln)][:60]
        return "\n".join(out) + "\n"
    log_fmt = ["--format=%h %ad %s", "--date=short"]
    versions = git_out(root, "log", "--follow", f"-n{limit}", *log_fmt, "--", name).strip().split("\n")
    versions = [v for v in versions if v]
    out.append(f"{name}: {len(versions)} version(s) (newest first, at most {limit})")
    out += [f"  {v}" for v in versions]
    for w in words:
        found = git_out(root, "log", "--follow", "-S", w, *log_fmt, "--", name).strip().split("\n")
        found = [x for x in found if x]
        out.append(f"commits where \"{w}\" appeared or vanished: {len(found)}")
        out += [f"  {x}" for x in found[:limit]]
    out.append("next: history ROOT FILE --at <hash> [--words ...] shows that version")
    return "\n".join(out) + "\n"


def toc(path):
    lines = read_lines(path)
    size = sum(len(x) + 1 for x in lines)
    heads = [(i + 1, len(m.group(1)), m.group(2)) for i, ln in enumerate(lines)
             for m in [HEADING_RE.match(ln)] if m]
    out = [f"{os.path.basename(path)} | {size} characters, {len(lines)} lines | headings: {len(heads)}"]
    starts = [1] + [h[0] for h in heads]
    ends = [h[0] - 1 for h in heads] + [len(lines)]
    titles = [(0, "(before the first heading)")] + [(lv, t) for _, lv, t in heads]
    for start, end, (level, title) in zip(starts, ends, titles):
        body = lines[start - 1:end] if level == 0 else lines[start:end]
        if level == 0 and not any(x.strip() for x in body):
            continue
        chars = sum(len(x) + 1 for x in body)
        items = sum(1 for x in body if ITEM_RE.match(x))
        rows = sum(1 for x in body if is_table_row(x) and not is_separator(x))
        extra = (f" | {items} items" if items else "") + (f" | {rows} table rows" if rows else "")
        out.append(f"{start}-{end} | {'#' * level + ' ' if level else ''}{title} | {chars} characters{extra}")
    return "\n".join(out) + "\n"


def main():
    kbconf.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find", help="matching blocks of the library's files")
    p.add_argument("root", help="library root folder")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--file", default="", help="only files whose name contains this")
    p.add_argument("--in", dest="folder", default="", help="a subfolder of the library instead of its root")
    p.add_argument("--all", action="store_true", help="a block must hold every keyword")
    p.add_argument("--max-blocks", type=int, default=30)
    p.add_argument("--max-per-file", type=int, default=10)
    p.add_argument("--max-chars", type=int, default=12000)
    p = sub.add_parser("toc", help="sections of one file with line ranges")
    p.add_argument("file")
    p = sub.add_parser("ask", help="one search for a question: summary files, index, sources, notes")
    p.add_argument("root", help="library root folder")
    p.add_argument("--q", action="append", required=True, metavar="WORDING[|WORDING...]",
                   help="one keyword with its wordings, separated by | (repeatable)")
    p.add_argument("--all", action="store_true", help="a block must hold a wording of every keyword")
    p.add_argument("--entities", action="store_true", help="also search the entities folder")
    p.add_argument("--max-files", type=int, default=5)
    p.add_argument("--max-chars", type=int, default=12000)
    p = sub.add_parser("history", help="earlier versions of one file from git")
    p.add_argument("root")
    p.add_argument("file", help="file name relative to the library root")
    p.add_argument("--words", nargs="*", default=[], help="when a wording appeared or vanished; with --at, its blocks")
    p.add_argument("--at", default="", help="a commit: show the file as it was then")
    p.add_argument("--limit", type=int, default=20)
    kbconf.add_log_args(ap)
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    if a.cmd == "ask":
        if not os.path.isdir(a.root):
            print(f"not a library folder: {a.root}", file=sys.stderr)
            return 2
        sys.stdout.write(ask(a.root, a.q, a.all, a.entities, a.max_files, budget=a.max_chars))
        return 0
    if a.cmd == "history":
        try:
            sys.stdout.write(history(a.root, a.file, a.words, a.at, a.limit))
        except RuntimeError as e:
            print(f"git failed: {e}")
            return 3
        return 0
    if a.cmd == "toc":
        if not os.path.isfile(a.file):
            print(f"not a file: {a.file}", file=sys.stderr)
            return 2
        sys.stdout.write(toc(a.file))
        return 0
    where = os.path.join(a.root, a.folder) if a.folder else a.root
    if not os.path.isdir(where) or (a.folder and (os.path.isabs(a.folder) or ".." in a.folder.replace("\\", "/").split("/"))):
        print(f"not a library folder: {where}", file=sys.stderr)
        return 2
    sys.stdout.write(find(a.root, a.keywords, a.file, a.folder, a.all, a.max_blocks, a.max_per_file, a.max_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
