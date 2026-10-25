#!/usr/bin/env python3
"""Change a summary file item by item instead of writing it out again whole.

  apply OLD PATCH.json --out NEW [--changes CHANGES.txt] [--check] [--min-ratio 0.7]

OLD is the current version (read from the library or its copy); NEW is written, OLD is never changed.
PATCH.json is a list of changes, applied together:

  {"op": "replace", "old": "<line(s)>", "new": "<text>"}
  {"op": "delete", "old": "<line(s)>", "reason": "<why>"}
  {"op": "insert_after", "anchor": "<line(s)>", "new": "<text>"}
  {"op": "insert_before", "anchor": "<line(s)>", "new": "<text>"}
  {"op": "set_field", "field": "<label>", "value": "<value>"}

"old" and "anchor" are one or more whole lines copied from OLD (trailing spaces aside); each must occur
exactly once, so add the line before or after when a line occurs more than once. "new" may hold several
lines. set_field changes the value of the first line that starts with the label followed by a colon
(last updated, version, entries; front matter too). Several inserts at one place keep their order.
Nothing is written when any change does not fit: a wording not found or found more than once, a field
not found, changes that overlap, an insert anchored on a line that is replaced or deleted.

It writes the change list for card_check.py (--changes, default NEW with .changes.txt), one line each:
  Item: <old wording> -> <new wording>
  Delete item: <old wording> (<reason>)
  Add: <new wording>
  Field <label>: <old value> -> <new value>
With --check it runs card_check.py OLD NEW --changes ... right after and exits with its result, so one
call patches and checks. NEW keeps OLD's line breaks as LF, its encoding as UTF-8 and its final newline.
A NEW inside a library root (next to _kb.json) is refused: patch into the work folder's out folder.

stdout: results. stderr: log. Exit codes: 0 ok; 2 bad arguments or unreadable file; 3 a change does not
fit (nothing written) or card_check failed.
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys

log = logging.getLogger("card_patch")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
HERE = os.path.dirname(os.path.abspath(__file__))
OPS = ("replace", "delete", "insert_after", "insert_before", "set_field")


class PatchError(Exception):
    pass


def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # not a reconfigurable text stream


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as e:
        log.error("cannot read %s: %s", path, e)
        sys.exit(2)


def in_library(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(d, "_kb.json")):
            return True
        up = os.path.dirname(d)
        if up == d:
            return False
        d = up


def as_lines(text):
    lines = [ln.rstrip() for ln in str(text).replace("\r\n", "\n").strip("\n").split("\n")]
    return lines if any(lines) else []


def locate(lines, want, what):
    """Start index of the one place where the lines `want` occur in a row."""
    if not want:
        raise PatchError(f"{what}: empty")
    n = len(want)
    at = [i for i in range(len(lines) - n + 1) if lines[i:i + n] == want]
    if not at:
        raise PatchError(f"{what}: not found: {short(want)}")
    if len(at) > 1:
        raise PatchError(f"{what}: found {len(at)} times (lines {', '.join(str(i + 1) for i in at[:5])}); "
                         f"add the line before or after to make it unique: {short(want)}")
    return at[0]


def short(lines, n=60):
    s = " / ".join(lines)
    return s if len(s) <= n else s[:n] + "…"


def field_re(label):
    return re.compile(r"^(\s*" + re.escape(label) + r"\s*[：:]\s*)(.*)$")


def plan(lines, ops):
    """[(kind, start, end, new lines, record)] sorted for applying; raises PatchError listing every problem."""
    problems, edits, spans, anchors = [], [], [], []
    for k, op in enumerate(ops, 1):
        what = f"change {k} ({op.get('op') if isinstance(op, dict) else '?'})"
        try:
            if not isinstance(op, dict) or op.get("op") not in OPS:
                raise PatchError(f"change {k}: op must be one of {', '.join(OPS)}")
            kind = op["op"]
            if kind == "set_field":
                label, value = str(op.get("field", "")).strip(), str(op.get("value", "")).strip()
                if not label or "\n" in value:
                    raise PatchError(f"{what}: needs a field label and a one-line value")
                rx = field_re(label)
                i = next((j for j, ln in enumerate(lines) if rx.match(ln)), None)
                if i is None:
                    raise PatchError(f"{what}: no line starts with {label}:")
                m = rx.match(lines[i])
                edits.append(("replace", i, i + 1, [m.group(1) + value],
                              f"Field {label}: {m.group(2).strip()} -> {value}", k))
                spans.append((i, i + 1, k))
                continue
            if kind in ("replace", "delete"):
                old = as_lines(op.get("old", ""))
                i = locate(lines, old, what)
                new = as_lines(op.get("new", "")) if kind == "replace" else []
                if kind == "replace" and not new:
                    raise PatchError(f"{what}: empty new text; use delete with a reason")
                if kind == "delete" and not str(op.get("reason", "")).strip():
                    raise PatchError(f"{what}: a deletion needs a reason")
                rec = (f"Item: {' '.join(old)} -> {' '.join(new)}" if kind == "replace" else
                       f"Delete item: {' '.join(old)} ({str(op['reason']).strip()})")
                edits.append(("replace", i, i + len(old), new, rec, k))
                spans.append((i, i + len(old), k))
            else:
                anchor = as_lines(op.get("anchor", ""))
                i = locate(lines, anchor, what)
                new = as_lines(op.get("new", ""))
                if not new:
                    raise PatchError(f"{what}: nothing to insert")
                at = i + len(anchor) if kind == "insert_after" else i
                edits.append(("insert", at, at, new, f"Add: {' '.join(new)}", k))
                anchors.append((i, i + len(anchor), k))
        except PatchError as e:
            problems.append(str(e))
    for a, (s1, e1, k1) in enumerate(spans):
        for s2, e2, k2 in spans[a + 1:]:
            if s1 < e2 and s2 < e1:
                problems.append(f"changes {k1} and {k2} overlap (lines {s1 + 1}-{e1} and {s2 + 1}-{e2})")
    for s1, e1, k1 in anchors:
        for s2, e2, k2 in spans:
            if s1 < e2 and s2 < e1:
                problems.append(f"change {k1} is anchored on lines that change {k2} replaces or deletes")
    if problems:
        raise PatchError("\n".join(problems))
    # Back to front, so earlier positions stay valid; at one position inserts come before a replace
    # starting there and keep their own order.
    return sorted(edits, key=lambda e: (e[1], 0 if e[0] == "insert" else 1, e[5]), reverse=True)


def apply(text, ops):
    lines = text.split("\n")
    final_newline = text.endswith("\n")
    if final_newline:
        lines = lines[:-1]
    stripped = [ln.rstrip() for ln in lines]
    edits = plan(stripped, ops)
    out = list(lines)
    for kind, start, end, new, _, _ in edits:
        out[start:end] = new
    records = [e[4] for e in sorted(edits, key=lambda e: e[5])]
    return "\n".join(out) + ("\n" if final_newline else ""), records


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("old")
    p.add_argument("patch")
    p.add_argument("--out", required=True)
    p.add_argument("--changes", help="change list to write (default: NEW.changes.txt)")
    p.add_argument("--check", action="store_true", help="run card_check.py on OLD and NEW afterwards")
    p.add_argument("--min-ratio", default="0.7", help="passed on to card_check.py")
    ap.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="default: LOG_LEVEL, else INFO")
    a = ap.parse_args()
    logging.basicConfig(level=a.log_level, format=LOG_FORMAT, stream=sys.stderr)
    if in_library(a.out):
        print(f"refused: {a.out} is inside a library root; write into the work folder's out folder")
        return 3
    try:
        ops = json.loads(read(a.patch))
        if not isinstance(ops, list):
            raise ValueError("expected a JSON list of changes")
    except ValueError as e:
        print(f"refused: {a.patch}: {e}")
        return 2
    old_text = read(a.old)
    try:
        new_text, records = apply(old_text, ops)
    except PatchError as e:
        for line in str(e).split("\n"):
            print(f"does not fit: {line}")
        print("Result: nothing written; copy the wording exactly from the file and run again")
        return 3
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)
    changes = a.changes or os.path.splitext(a.out)[0] + ".changes.txt"
    with open(changes, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(records) + ("\n" if records else ""))
    count = {k: sum(1 for op in ops if op.get("op") == k) for k in OPS}
    print(f"patched: {count['replace']} replaced, {count['delete']} deleted, "
          f"{count['insert_after'] + count['insert_before']} inserted, {count['set_field']} fields -> {a.out}")
    print(f"change list: {changes}")
    log.info("old %d lines, new %d lines", old_text.count("\n"), new_text.count("\n"))
    if not a.check:
        return 0
    p = subprocess.run([sys.executable, os.path.join(HERE, "card_check.py"), a.old, a.out, "--changes", changes,
                        "--min-ratio", str(a.min_ratio)], stdout=subprocess.PIPE, text=True, encoding="utf-8",
                       errors="replace")
    print(p.stdout.rstrip("\n"))
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
