#!/usr/bin/env python3
"""Health check of a library on disk (references/lint.md) in one call: report only, nothing changes.

  lint.py ROOT --work WORK [--all] [--days 30] [--max-sources 20] [--list 20]

ROOT is the library root (a checkout of a GitHub library). The scope is the topic files changed in the
last --days days (by git history, else by file time), or every file with --all. It prints the fixed
report of lint.md, each list capped at --list lines with its total:

  1 stray files          names the skills never use as a source, files that are not .md
  2 same-name copies     not applicable on disk: a folder holds one file per name
  3 Table E and pages    entities without a page, pages without an entity, pages without an identity
                         line, related-files lists out of date (entity_pages.py --in-place fixes them)
  4 format (YAML mode)   no front matter; fields most files have but this one lacks; dates not ISO;
                         links to names outside Table E; partition differing from the file name;
                         topic not found in Table A
  5 suspicious dates     a year-month in the file name more than two months after the document date
  6 basis lines          status-card lines naming a basis without a link; links whose file is
                         neither in the root nor in the index
  7 core overviews       core entity pages last changed before the newest document linking them
  8 index                index rows without a file, files in scope missing from the index
  9 settings             kbconf validate, Table A against partitions.max and fallback, _kb-params.md
  10 duplicate entities  Table E names and aliases that match once case, spaces, hyphens and
                         punctuation are dropped (high), or where one holds the other (medium):
                         candidates for the assistant to judge
  11 quick notes         count and oldest
  12 consolidation queue rows, oldest, rows without a file, marked files without a row
  13 status-card values  evidence_check.py on the items whose basis files are in scope, at most
                         --max-sources basis files (copied into WORK/lint/sources)
  14 class-A data        with sensitivity enabled: candidates in the files in scope (starred)

stdout: the report. stderr: log. Exit codes: 0 report printed; 2 bad arguments.
"""
import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entity_pages  # noqa: E402
import kbconf  # noqa: E402

log = logging.getLogger("lint")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_FILES = {"README.md", "CLAUDE.md", "AGENTS.md"}
EXPECTED = {"_kb.json", "_kb-params.md", "kb-libraries.json"}
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.md)(?:#[^)]*)?\)")
BASIS_RE = re.compile(r"依据|basis|source", re.I)
ITEM_RE = re.compile(r"^\s*(?:第\s*(\d+)\s*条|item\s*(\d+)|(\d+)\s*[.、．)）])", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$")
NAME_YM = re.compile(r"(?<!\d)(20\d{2})[-_.年]?(0[1-9]|1[0-2]|[1-9](?=月))(?:月|(?!\d))")
STAMP_RE = re.compile(r"\d{8}")
PENDING = "<!-- kb:conclusions-pending -->"
PART_KEYS = ("partition", "分区")
TOPIC_KEYS = ("topic", "议题")


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


def squash(s):
    return re.sub(r"[\s\-_.·・()（）\[\]【】]+", "", s.casefold())


def git(root, *args):
    p = subprocess.run(["git", "-C", root, "-c", "core.quotepath=false", *args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else None


class Library:
    def __init__(self, root):
        self.root = root
        self.cfg = kbconf.load_library(root)
        self.names = self.cfg["names"]
        self.files = sorted(f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f)))
        self.summary = {}
        for key in kbconf.SUMMARY_KEYS:
            n = self.names[key]
            if n in self.files:
                self.summary[key] = n
                continue
            k = self.names.get(f"{key}_key") or kbconf.search_key(n)
            hit = [f for f in self.files if f.endswith(".md") and k in f and not f.startswith(("_", "."))]
            if hit:
                self.summary[key] = hit[0]
        self.spec = read(os.path.join(root, self.summary["spec"])) if "spec" in self.summary else ""
        self.ents = (kbconf.entity_list(self.spec) or []) if self.spec else []
        self.table_a = kbconf.spec_table(self.spec, "A") if self.spec else None
        self.section_a = kbconf.spec_section(self.spec, "A") if self.spec else None
        self.is_git = git(root, "rev-parse", "--is-inside-work-tree") is not None
        self._cache = {}

    def ignored(self, name):
        n = self.names
        stem = name[:-3] if name.endswith(".md") else name
        return (not name.endswith(".md") or name.startswith(("_", ".", n["snapshot_prefix"])) or name in REPO_FILES
                or (n["old_suffix"] and n["old_suffix"] in stem and bool(STAMP_RE.search(stem.split(n["old_suffix"])[-1]))))

    def topic_files(self):
        return [f for f in self.files if not self.ignored(f) and f not in self.summary.values()]

    def text(self, rel):
        if rel not in self._cache:
            self._cache[rel] = read(os.path.join(self.root, rel))
        return self._cache[rel]

    def changed_since(self, days):
        """Root and entity files changed in the last days, or None when that cannot be told by git."""
        if not self.is_git:
            return None
        out = git(self.root, "log", f"--since={days}.days", "--name-only", "--format=")
        if out is None:
            return None
        return {x.strip() for x in out.split("\n") if x.strip()}

    def last_change(self, rel):
        if self.is_git:
            out = git(self.root, "log", "-1", "--format=%ad", "--date=short", "--", rel)
            if out and out.strip():
                return out.strip()
        return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.root, rel))).strftime("%Y-%m-%d")


def has_identity(text):
    """True when the first line after the page title is text, not a heading, a mark or a code fence."""
    seen_title = False
    for line in text[text.find("\n---", 4) + 4:].split("\n") if text.startswith("---\n") else text.split("\n"):
        x = line.strip()
        if not x:
            continue
        if not seen_title:
            seen_title = x.startswith("# ")
            continue
        return not x.startswith(("#", "<!--", "```"))
    return False


def doc_date(fm):
    """The earliest ISO date among the date fields, as YYYY-MM-DD, or None."""
    vals = [unquote(v)[:10] for k, v in (fm or {}).items() if ("date" in k.casefold() or "日期" in k)
            and ISO_RE.match(unquote(v))]
    return min(vals) if vals else None


def capped(items, n):
    out = [f"   {x}" for x in items[:n]]
    if len(items) > n:
        out.append(f"   ... {len(items)} in total, first {n} shown")
    return out


def run(lib, work, scope_all, days, max_sources, cap):
    names, root = lib.names, lib.root
    topics = lib.topic_files()
    changed = None if scope_all else lib.changed_since(days)
    if scope_all:
        scope, how = topics, "all files"
    elif changed is not None:
        scope, how = [f for f in topics if f in changed], f"changed in the last {days} days (git)"
    else:
        cutoff = datetime.now().timestamp() - days * 86400
        scope = [f for f in topics if os.path.getmtime(os.path.join(root, f)) >= cutoff]
        how = f"modified in the last {days} days (file time)"
    fms = {f: front_matter(lib.text(f)) for f in scope}
    out = [f"Date: {date.today().isoformat()} | library: {lib.cfg.get('label') or os.path.basename(root)} | "
           f"scope: {len(scope)} of {len(topics)} topic files, {how}"]

    # 1 stray files
    expected = EXPECTED | {names["consolidation_queue"]} | ({(lib.cfg.get("inbox") or {}).get("config")} - {None})
    stray = [f for f in lib.files if f not in expected and not f.startswith(".") and f not in REPO_FILES
             and lib.ignored(f)]
    out.append(f"1. Stray files: {len(stray)}")
    out += capped(stray, cap)

    # 2 same-name copies
    out.append("2. Same-name copies: not applicable (a folder on disk holds one file per name)")

    # 3 Table E and entity pages
    ent_dir = os.path.join(root, names["entities_dir"])
    pages = {f[:-3] for f in os.listdir(ent_dir) if f.endswith(".md")} if os.path.isdir(ent_dir) else set()
    ent_names = {n for n, _ in lib.ents}
    no_page = sorted(ent_names - pages)
    no_ent = sorted(pages - ent_names)
    no_id = sorted(n for n in pages if not has_identity(read(os.path.join(ent_dir, n + ".md"))))
    stale_lists = [n for n, _, _ in entity_pages.changes(root, lib.cfg)] if pages else []
    out.append(f"3. Table E and entity pages: {len(no_page) + len(no_ent) + len(no_id) + len(stale_lists)}"
               + ("" if lib.ents else " (Table E not read from the spec)"))
    out += capped([f"no page: {n}" for n in no_page] + [f"no Table E row: {names['entities_dir']}/{n}.md" for n in no_ent]
                  + [f"no identity line: {names['entities_dir']}/{n}.md" for n in no_id]
                  + [f"related files out of date: {names['entities_dir']}/{n}.md" for n in stale_lists], cap)

    # 4 format
    problems = []
    yaml_mode = lib.cfg.get("metadata", "yaml") == "yaml"
    if yaml_mode:
        all_fms = [front_matter(lib.text(f)) for f in topics]
        with_fm = [fm for fm in all_fms if fm is not None]
        common = sorted(k for k in {k for fm in with_fm for k in fm}
                        if with_fm and sum(1 for fm in with_fm if k in fm) >= 0.9 * len(with_fm))
        known = {squash(x) for n, al in lib.ents for x in [n] + al}
        a_text = "\n".join(lib.section_a or [])
        for f in scope:
            fm = fms[f]
            if fm is None:
                problems.append(f"{f}: no front matter")
                continue
            miss = [k for k in common if k not in fm]
            if miss:
                problems.append(f"{f}: missing {', '.join(miss)} (present in 90% of files)")
            for k, v in fm.items():
                if ("date" in k.casefold() or "日期" in k) and v and not ISO_RE.match(unquote(v)):
                    problems.append(f"{f}: {k} not an ISO date: {unquote(v)[:30]}")
            outside = sorted({x for v in fm.values() for x in WIKI_RE.findall(v)
                              if lib.ents and squash(x) not in known})
            if outside:
                problems.append(f"{f}: links outside Table E: {', '.join(outside[:5])}")
            part = next((unquote(fm[k]) for k in PART_KEYS if k in fm), None)
            if part and not f.startswith(part + "_"):
                problems.append(f"{f}: partition {part} differs from the file name")
            topic = next((unquote(fm[k]) for k in TOPIC_KEYS if k in fm), None)
            if topic and a_text and topic not in a_text and topic.replace("-", " ") not in a_text:
                problems.append(f"{f}: topic not in Table A: {topic}")
    out.append(f"4. Format problems: {len(problems)}" + ("" if yaml_mode else " (text metadata: not checked)"))
    out += capped(problems, cap)

    # 5 suspicious dates
    sus = []
    for f in scope:
        d = doc_date(fms[f])
        m = NAME_YM.search(f)
        if not (d and m):
            continue
        ny, nm = int(m.group(1)), int(m.group(2))
        dy, dm = int(d[:4]), int(d[5:7])
        if (ny * 12 + nm) - (dy * 12 + dm) > 2:
            sus.append(f"{f}: name {ny}-{nm:02d}, document date {d}")
    out.append(f"5. Suspicious dates: {len(sus)}")
    out += capped(sus, cap)

    # 6 basis lines
    index_rows = set()
    idx_path = os.path.join(root, lib.summary["index"]) if "index" in lib.summary else None
    if idx_path:
        for line in lib.text(lib.summary["index"]).split("\n"):
            cells = [c.strip() for c in re.split(r"[|｜]", line.strip().strip("|｜"))]
            if cells and cells[0].lower().endswith(".md"):
                index_rows.add(cells[0])
    card_lines = lib.text(lib.summary["status_card"]).split("\n") if "status_card" in lib.summary else []
    unlinked, broken = 0, []
    existing = set(lib.files) | {f"{names['entities_dir']}/{p}.md" for p in pages}
    for no, line in enumerate(card_lines, 1):
        links = [x.strip() for x in WIKI_RE.findall(line)] + MDLINK_RE.findall(line)
        if BASIS_RE.search(line) and not links:
            unlinked += 1
        for x in links:
            target = x if x.endswith(".md") else x + ".md"
            if (target not in existing and os.path.basename(target) not in index_rows
                    and os.path.basename(target)[:-3] not in pages):
                broken.append(f"status card line {no}: {x}")
    out.append(f"6. Basis lines: {unlinked} not linked, {len(broken)} broken"
               + ("" if card_lines else " (status card not found)"))
    out += capped(broken, cap)

    # 7 core entity overviews
    stale = []
    core = [n for n in pages if re.search(r"^(core|核心)\s*:\s*(true|是|yes)\s*$",
                                          read(os.path.join(ent_dir, n + ".md"))[:2000], re.M | re.I)]
    if core:
        newest = {}
        for f in topics:
            fm = front_matter(lib.text(f))
            d = doc_date(fm)
            if not (fm and d):
                continue
            for x in {x.strip() for v in fm.values() for x in WIKI_RE.findall(v)}:
                if x in core and d > newest.get(x, ""):
                    newest[x] = d
        for n in sorted(core):
            last = lib.last_change(f"{names['entities_dir']}/{n}.md")
            if n in newest and newest[n] > last:
                stale.append(f"{names['entities_dir']}/{n}.md: changed {last}, newest linked document {newest[n]}")
    out.append(f"7. Overviews possibly stale: {len(stale)} (of {len(core)} core entities)")
    out += capped(stale, cap)

    # 8 index
    if idx_path:
        no_file = sorted(r for r in index_rows if r not in lib.files)
        missing = sorted(f for f in scope if f not in index_rows)
        out.append(f"8. Index mismatches: {len(no_file) + len(missing)}")
        out += capped([f"row without file: {r}" for r in no_file] + [f"not in the index: {f}" for f in missing], cap)
    else:
        out.append("8. Index mismatches: index not found")

    # 9 settings
    settings = []
    try:
        settings += kbconf.validate(kbconf.load_json(kbconf.find_kb_json(root)))
    except kbconf.ConfigError as e:
        settings.append(str(e))
    parts = lib.cfg.get("partitions") or {}
    if lib.section_a is not None:
        firsts = [r[0] for r in lib.table_a[1] if r] if lib.table_a else [ln.strip() for ln in lib.section_a]
        nums = sorted({int(m.group(1)) for x in firsts for m in [re.match(r"^(\d{2})(?!\d)", x)] if m})
        if not nums:
            settings.append("no partition numbers found in Table A")
        if nums and parts.get("max") and max(nums) != int(parts["max"]):
            settings.append(f"partitions.max is {parts['max']}, Table A ends at {max(nums):02d}")
        fb = str(parts.get("fallback") or "")
        if fb and nums and int(fb) not in nums:
            settings.append(f"partitions.fallback {fb} is not a partition in Table A")
        if not fb:
            settings.append("partitions.fallback is not set")
    else:
        settings.append("Table A not read from the spec: partitions not compared")
    if kbconf.PARAMS_FILE not in lib.files:
        settings.append(f"{kbconf.PARAMS_FILE} missing")
    out.append("9. Settings: " + ("consistent" if not settings else f"{len(settings)} mismatches"))
    out += capped(settings, cap)

    # 10 duplicate entities
    groups = []
    flat = [(n, x) for n, al in lib.ents for x in [n] + al if len(x) >= 2]
    seen = set()
    for i, (n1, x1) in enumerate(flat):
        for n2, x2 in flat[i + 1:]:
            if n1 == n2 or (n1, n2) in seen or (n2, n1) in seen:
                continue
            a, b = squash(x1), squash(x2)
            short, long_ = sorted((a, b), key=len)
            if a == b:
                conf = "high: only case, spaces, hyphens or punctuation differ"
            elif len(short) >= 2 and short in long_ and len(short) * 2 >= len(long_):
                conf = "medium: one name holds the other"
            else:
                continue
            seen.add((n1, n2))
            groups.append(f"{n1} / {n2} ({x1} ~ {x2}); {conf}")
    out.append(f"10. Possible duplicate entities (name forms only; judge translations and abbreviations yourself): {len(groups)} groups")
    out += capped(groups, cap)

    # 11 quick notes
    notes_dir = os.path.join(root, names["notes_dir"])
    if os.path.isdir(notes_dir):
        notes = sorted(f for f in os.listdir(notes_dir) if f.endswith(".md") and os.path.isfile(os.path.join(notes_dir, f)))
        stamps = sorted(m.group(0) for f in notes for m in [re.match(r"\d{8}", f)] if m)
        oldest = f"{stamps[0][:4]}-{stamps[0][4:6]}-{stamps[0][6:]}" if stamps else "unknown"
        out.append(f"11. Quick-note backlog: {len(notes)} notes" + (f", oldest {oldest}" if notes else ""))
    else:
        out.append("11. Quick-note backlog: no notes folder")

    # 12 consolidation queue
    queue = os.path.join(root, names["consolidation_queue"])
    pending = sorted(f for f in scope if PENDING in lib.text(f))
    if os.path.isfile(queue):
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in read(queue).split("\n")
                if ln.strip().startswith("|") and ".md" in ln]
        rows = [r for r in rows if r and r[0].endswith(".md")]
        times = sorted(r[2] for r in rows if len(r) > 2 and r[2])
        no_file = [r[0] for r in rows if r[0] not in lib.files]
        no_row = [f for f in pending if f not in {r[0] for r in rows}]
        out.append(f"12. Consolidation backlog: {len(rows)} files" + (f", oldest {times[0]}" if times else "")
                   + f"; {len(no_file)} rows without file, {len(no_row)} marked files without row")
        out += capped([f"row without file: {x}" for x in no_file] + [f"marked, no row: {x}" for x in no_row], cap)
    else:
        out.append("12. Consolidation backlog: no queue" + (f"; {len(pending)} marked files without row" if pending else ""))
        out += capped(pending, cap)

    # 13 status-card values
    if card_lines:
        items, bases = [], []
        for line in card_lines:
            m = ITEM_RE.match(line)
            links = [x.strip() for x in WIKI_RE.findall(line)] + MDLINK_RE.findall(line)
            if not (m and links):
                continue
            files = [x if x.endswith(".md") else x + ".md" for x in links]
            if not all(f in lib.files or os.path.isfile(os.path.join(ent_dir, os.path.basename(f))) for f in files):
                continue  # a broken link is check 6's; its values cannot be looked up
            if scope_all or any(f in scope for f in files):
                items.append((next(g for g in m.groups() if g), files))
                bases += [f for f in files if f not in bases]
        sampled = len(bases) > max_sources
        if sampled:
            dated = sorted(bases, key=lambda f: doc_date(front_matter(lib.text(f))) or "" if f in lib.files else "",
                           reverse=True)
            bases = dated[:max_sources]
        chosen = [n for n, files in items if all(f in bases for f in files)]
        if chosen:
            lint_dir = os.path.join(work, "lint")
            src_dir = os.path.join(lint_dir, "sources")
            shutil.rmtree(lint_dir, ignore_errors=True)
            os.makedirs(src_dir)
            for f in bases:
                for cand in (os.path.join(root, f), os.path.join(ent_dir, os.path.basename(f))):
                    if os.path.isfile(cand):
                        shutil.copy2(cand, os.path.join(src_dir, os.path.basename(f)))
                        break
            card_copy = os.path.join(lint_dir, lib.summary["status_card"])
            shutil.copy2(os.path.join(root, lib.summary["status_card"]), card_copy)
            args = [sys.executable, os.path.join(HERE, "evidence_check.py"), card_copy, "--sources", src_dir]
            for n in chosen:
                args += ["--item", n]
            p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                               encoding="utf-8", errors="replace")
            report = [ln for ln in p.stdout.rstrip("\n").split("\n") if ln.strip()]
            out.append(f"13. Status-card values: {len(chosen)} items checked ({'sampled' if sampled else 'all in scope'}, "
                       f"{len(bases)} basis files)")
            out += capped(report, cap * 2)
        else:
            out.append("13. Status-card values: no numbered item with a basis link in scope")
    else:
        out.append("13. Status-card values: status card not found")

    # 14 class-A data
    sens = lib.cfg.get("sensitivity") or {}
    if sens.get("enabled"):
        paths = [os.path.join(root, f) for f in scope] + [os.path.join(root, v) for v in lib.summary.values()]
        hits = kbconf.scan_files(paths, int(sens.get("keep_last", 4)))
        out.append(f"14. Class-A candidates: {len(hits)}")
        out += capped([f"{os.path.relpath(p, root)} line {no}: {kind}: {v}" for p, no, kind, v in hits], cap)
    return "\n".join(out) + "\n"


def main():
    kbconf.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", help="library root")
    ap.add_argument("--work", required=True, help="work folder (evidence-check copies go to WORK/lint)")
    ap.add_argument("--all", action="store_true", help="every topic file instead of the recent ones")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--max-sources", type=int, default=20, help="basis files copied for check 13")
    ap.add_argument("--list", type=int, default=20, help="lines listed per check")
    kbconf.add_log_args(ap)
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    try:
        lib = Library(os.path.abspath(a.root))
    except kbconf.ConfigError as e:
        print(f"error: {e}")
        return 2
    if os.path.abspath(a.work).startswith(lib.root + os.sep):
        print("refused: the work folder must be outside the library root")
        return 2
    sys.stdout.write(run(lib, os.path.abspath(a.work), a.all, a.days, a.max_sources, a.list))
    return 0


if __name__ == "__main__":
    sys.exit(main())
