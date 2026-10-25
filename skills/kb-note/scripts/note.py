#!/usr/bin/env python3
"""Save one quick note into a library on disk (kb-note, step 4 and 5) in one call.

  note.py save ROOT --topic "<short topic>" --body NOTE.txt [--title "<commit title>"]

ROOT is the library root (a checkout of a GitHub library); NOTE.txt holds the finished note in the
layout of SKILL.md step 3, written by the assistant into the work folder. The script:
  0. in a git checkout, first brings it up to date (kbgit.py sync, which also switches it to the
     default branch); when that stops (exit 3 or 4), nothing is written and its line is reported;
  1. names the file YYYYMMDD-HHMM_<short topic>.md in the library time zone; punctuation and slashes
     leave the topic, spaces become hyphens; a second note in the same minute gets -2, -3 after the time;
  2. with sensitivity enabled, refuses a note that still holds class-A data (kbconf.py scan-a; the
     reply shows only starred values), so it can be masked and saved again;
  3. creates the notes folder (names.notes_dir) when it is missing and writes the note as a new file,
     never over an existing one;
  4. in a git checkout, commits and pushes the one file (kbgit.py commit; the title defaults to
     "Quick note: <file name>", in Chinese 「随手记：<文件名>」); the note counts as saved only after "pushed:";
  5. checks the file is there and prints the backlog: notes waiting and the oldest, and "remind" when
     there are more than 20 or the oldest is older than 14 days.

stdout: results. stderr: log. Exit codes: 0 saved (and pushed); 2 bad arguments; 3 refused (class-A data,
empty note, the checkout cannot be synced); 4 remote unreachable before writing, nothing written; 4 or 5
after "written:", written but not pushed (remote unreachable, push failed): say so.
"""
import argparse
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbconf  # noqa: E402

log = logging.getLogger("note")
HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = re.compile(r"^(\d{8})-(\d{4})")


def clean_topic(topic):
    t = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", topic)
    t = re.sub(r"[，。、；：！？,.;:!?（）()【】\[\]{}「」『』《》“”‘’'`~@#$%^&+=]", " ", t)
    return re.sub(r"-{2,}", "-", re.sub(r"\s+", "-", t.strip())).strip("-")


def note_name(folder, stamp, topic):
    names = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    same_minute = [n for n in names if n.startswith(stamp)]
    if not same_minute:
        return f"{stamp}_{topic}.md"
    k = 2
    while any(n.startswith(f"{stamp}-{k}_") for n in names):
        k += 1
    return f"{stamp}-{k}_{topic}.md"


def backlog(folder, now):
    notes = sorted(f for f in os.listdir(folder) if f.endswith(".md") and os.path.isfile(os.path.join(folder, f)))
    stamps = sorted(m.group(1) for f in notes for m in [STAMP.match(f)] if m)
    if not stamps:
        return len(notes), None, False
    oldest = datetime.strptime(stamps[0], "%Y%m%d").date()
    remind = len(notes) > 20 or (now.date() - oldest) > timedelta(days=14)
    return len(notes), oldest, remind


def cmd_save(a):
    try:
        cfg = kbconf.load_library(a.root)
    except kbconf.ConfigError as e:
        print(f"error: {e}")
        return 2
    root, names = os.path.dirname(cfg["_path"]), cfg["names"]
    try:
        with open(a.body, encoding="utf-8") as f:
            body = f.read().replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read {a.body}: {e}")
        return 2
    if not body.strip():
        print("refused: the note is empty")
        return 3
    topic = clean_topic(a.topic)
    if not topic:
        print("refused: the short topic is empty once punctuation and slashes are removed")
        return 3
    sens = cfg.get("sensitivity") or {}
    if sens.get("enabled"):
        hits = kbconf.scan_class_a(body, int(sens.get("keep_last", 4)))
        if hits:
            for no, kind, v in hits:
                print(f"class-A candidate: line {no}: {kind}: {v}")
            print(f"refused: {len(hits)} class-A candidate(s); mask them in the note (at most the last "
                  f"{sens.get('keep_last', 4)} characters) and save again. Nothing is written.")
            return 3
    try:
        now = kbconf.now(cfg["timezone"])
    except kbconf.ConfigError as e:
        print(f"error: {e}")
        return 2
    if os.path.isdir(os.path.join(root, ".git")):
        p = subprocess.run([sys.executable, os.path.join(HERE, "kbgit.py"), "sync", root], stdout=subprocess.PIPE,
                           text=True, encoding="utf-8", errors="replace")
        print(p.stdout.rstrip("\n"))
        if p.returncode:
            print("not saved: the checkout could not be brought up to date (see above). Nothing is written.")
            return p.returncode
    folder = os.path.join(root, names["notes_dir"])
    created = not os.path.isdir(folder)
    os.makedirs(folder, exist_ok=True)
    name = note_name(folder, now.strftime("%Y%m%d-%H%M"), topic)
    path = os.path.join(folder, name)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(body if body.endswith("\n") else body + "\n")
    except FileExistsError:
        print(f"refused: {name} exists already")
        return 3
    print(f"written: {names['notes_dir']}/{name}" + (" (notes folder created)" if created else ""))
    code = 0
    if os.path.isdir(os.path.join(root, ".git")):
        zh = str(cfg.get("language", "")).lower().startswith("zh")
        title = a.title or (f"随手记：{name}" if zh else f"Quick note: {name}")
        p = subprocess.run([sys.executable, os.path.join(HERE, "kbgit.py"), "commit", root, "--title", title,
                            "--path", f"{names['notes_dir']}/{name}"], stdout=subprocess.PIPE, text=True,
                           encoding="utf-8", errors="replace")
        print(p.stdout.rstrip("\n"))
        code = p.returncode
        if code:
            print("not saved yet: the note is written in the checkout but not pushed (see above)")
    if not os.path.isfile(path):
        print("error: the note is not found after writing")
        return 3
    n, oldest, remind = backlog(folder, now)
    print(f"backlog: {n} note(s) waiting" + (f", oldest {oldest.isoformat()}" if oldest else "")
          + (" | remind" if remind else ""))
    return code


def main():
    kbconf.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    kbconf.add_log_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("save")
    p.add_argument("root", help="library root")
    p.add_argument("--topic", required=True, help="a few words summing up the note")
    p.add_argument("--body", required=True, help="file holding the finished note")
    p.add_argument("--title", help="commit title (default: Quick note: <file name>)")
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    return cmd_save(a)


if __name__ == "__main__":
    sys.exit(main())
