#!/usr/bin/env python3
"""Check and deliver the output of an intake run.

Output directory layout (the only accepted shape):
  OUT/*.md, OUT/README.txt        knowledge files, summary files and the readme (names starting with an
                                  underscore are refused, except the consolidation queue)
  OUT/<entities_dir>/*.md         entity pages (optional, no deeper folders)
  OUT/<sources_dir>/*             copies of originals, any format, named after their topic files
                                  (optional: a local library that keeps originals; refused with --in-place)

When a topic file gets a new version, the originals kept for its old version (<sources_dir>/<stem>.*)
move to the archive folder with it, unless the run delivers a copy under exactly the same name,
which is archived the usual way.

Subcommands:
  preview  OUT --library LIB --plan plan.json
           Local backend, round 1: list what will be written and which existing files will
           move to the archive folder. Nothing is changed.
  deliver  --plan plan.json
           Local backend, round 2 (after the user confirms): re-check every target, archive
           the old version (<stem><old_suffix><YYYYMMDDHHMMSS><ext>), copy the new one in,
           keep the readme in the archive folder and write a run log there.
  --in-place (preview): GitHub backend. An existing file with an output name is overwritten in place
           (git history keeps the old version): nothing moves to an archive folder, and deliver keeps
           the readme and run log next to the plan, in the work folder, instead of in the library.
           In YAML mode it also refreshes the related-files lists of the entity pages the delivery changes
           (entity_pages.py: written into WORK/related/, WORK being the folder of the plan) and delivers
           them with the rest.
  --confirmed (preview): a batch or fast intake run that the user confirmed at its start; deliver right
           after the preview, in the same call.
  --commit TITLE (deliver, or preview with --confirmed): GitHub backend. After a delivery without
           failures, commit and push exactly the files it wrote, with the run log as the message body
           (kbgit.py commit, which also takes the identity from the repository instructions). A
           delivery is complete only when this push succeeded; exit 5 means delivered but not pushed.
  Class-A check (preview): with sensitivity enabled in _kb.json, every output file is scanned
           (kbconf.py scan-a) and a candidate stops the preview with exit 3, unless --class-a-reviewed
           says the user confirmed them.
  --run RUN.json (preview): fast intake delivers each item on its own. Within one
           run the file index and the consolidation queue are archived the first time only and then
           replaced (their copy from before the run is in the archive folder already); deliver
           appends to one readme and one run log per run. RUN.json lives in the work folder and is
           started on first use.

LIB is the library root (or its _kb.json); every name comes from its "names", the time
stamps from its "timezone" and the file name limit from --max-name-len (Table D).
Results on stdout, logs on stderr. Exit codes: 0 ok, 2 bad input, 3 check failed, 4 I/O error.
"""
import argparse
import difflib
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entity_pages  # noqa: E402
import kbconf  # noqa: E402

log = logging.getLogger("package")
REPO_FILES = {"README.md", "CLAUDE.md", "AGENTS.md"}  # GitHub backend: never knowledge files


def check_output(out, names, max_len, allow_sources=False):
    """Return (files, errors). files = list of (relative path, absolute path)."""
    errors, files = [], []
    if not os.path.isdir(out):
        return [], [f"output directory not found: {out}"]
    ent, src = names["entities_dir"], names["sources_dir"]
    for entry in sorted(os.listdir(out)):
        p = os.path.join(out, entry)
        if os.path.isdir(p):
            if entry == src and not allow_sources:
                errors.append(f"{src}/ (originals) is delivered only into a local library that keeps originals")
                continue
            if entry not in (ent, src):
                errors.append(f"folder not allowed in the output: {entry} (only {ent}/ and {src}/)")
                continue
            for sub in sorted(os.listdir(p)):
                sp = os.path.join(p, sub)
                if os.path.isdir(sp):
                    errors.append(f"{entry}/ must not contain folders: {sub}")
                else:
                    files.append((f"{entry}/{sub}", sp))
        else:
            files.append((entry, p))
    rel = [r for r, _ in files]
    if names["index"] not in rel:
        errors.append(f"missing {names['index']} (every run rewrites it)")
    if names["readme"] not in rel:
        errors.append(f"missing {names['readme']}")
    for r, p in files:
        b = os.path.basename(r)
        if names["old_suffix"] in b or b.startswith(names["snapshot_prefix"]) or \
                (b.startswith("_") and r != names["consolidation_queue"]):
            errors.append(f"file that must not be delivered: {r}")
        elif r.startswith(src + "/"):  # an original: any format, kept as it is
            if not os.path.getsize(p):
                errors.append(f"empty file: {r}")
            log.info("included: %s (%d bytes)", r, os.path.getsize(p))
            continue
        elif not (b.lower().endswith(".md") or r == names["readme"]):
            errors.append(f"only .md files and {names['readme']} may be delivered: {r}")
        try:
            with open(p, encoding="utf-8") as f:
                if not f.read().strip():
                    errors.append(f"empty file: {r}")
        except UnicodeDecodeError:
            errors.append(f"not UTF-8: {r}")
        if max_len and len(b) > max_len:
            log.warning("file name longer than %d characters (%d): %s", max_len, len(b), b)
        log.info("included: %s (%d bytes)", r, os.path.getsize(p))
    return files, errors


def load_names(lib):
    try:
        cfg = kbconf.load_library(lib)
    except kbconf.ConfigError as e:
        log.error("%s", e)
        sys.exit(2)
    return cfg


def cmd_preview(a):
    cfg = load_names(a.library)
    names = cfg["names"]
    root = os.path.dirname(cfg["_path"])
    files, errors = check_output(a.out, names, a.max_name_len, allow_sources=not a.in_place)
    if a.in_place:  # repository files belong to the repository, never to an intake
        errors += [f"repository file must not be delivered: {r}" for r, _ in files
                   if r in REPO_FILES or os.path.basename(r).startswith(".")]
    for e in errors:
        print(f"Error: {e}")
    if errors:
        print("Result: check failed, nothing planned")
        sys.exit(3)
    if a.in_place and cfg.get("metadata", "yaml") == "yaml":
        files = with_related_lists(root, cfg, files, os.path.dirname(os.path.abspath(a.plan)))
    sens = cfg.get("sensitivity") or {}
    if sens.get("enabled") and not a.class_a_reviewed:
        hits = kbconf.scan_files([p for _, p in files], int(sens.get("keep_last", 4)))
        if hits:
            rel = {p: r for r, p in files}
            for p, no, kind, v in hits[:30]:
                print(f"Class-A candidate: {rel.get(p, p)} line {no}: {kind}: {v}")
            print(f"Result: {len(hits)} class-A candidate(s), nothing planned. Mask them in the output and preview "
                  "again; when the user confirmed each one is not class-A data (an order or serial number), "
                  "preview again with --class-a-reviewed and name them in the delivery note.")
            sys.exit(3)
    stamp0 = kbconf.now(cfg["timezone"]).replace(microsecond=0)
    run = load_run(a.run, cfg["timezone"])
    if run and not os.path.isfile(a.run):
        save_run(a.run, run)  # fixes the run's start time, which names its readme and run log
    again = rewritten(names) & set(run["archived"]) if run else set()
    items, seq = [], 0
    stale = [] if a.in_place else stale_originals(root, names, files)
    for r, p in files + stale:
        if r == names["readme"]:
            continue
        target = os.path.join(root, *r.split("/"))
        item = {"rel": r, "src": os.path.abspath(p) if p else None, "target": target,
                "src_size": os.path.getsize(p) if p else 0, "exists": os.path.exists(target)}
        if item["exists"]:
            st = os.stat(target)
            item.update(old_size=st.st_size, old_mtime=st.st_mtime)
            if a.in_place or (r in again and p):
                item["replace"] = True
            else:
                stem, ext = os.path.splitext(os.path.basename(target))
                stamp = (stamp0 + timedelta(seconds=seq)).strftime("%Y%m%d%H%M%S")
                seq += 1
                item["archive_as"] = f"{stem}{names['old_suffix']}{stamp}{ext}"
        items.append(item)
    log_dir = os.path.dirname(os.path.abspath(a.plan)) if a.in_place else os.path.join(root, names["archive_dir"])
    plan = {"library": cfg.get("label") or os.path.basename(root), "root": root,
            "archive_dir": log_dir, "in_place": bool(a.in_place),
            "readme": os.path.abspath(os.path.join(a.out, names["readme"])),
            "timezone": cfg["timezone"], "log_prefix": names["run_log_prefix"],
            "base_time": stamp0.strftime("%Y-%m-%d %H:%M:%S"), "items": items,
            "run": os.path.abspath(a.run) if a.run else "", "run_start": run["start"] if run else "",
            "rewritten": sorted(rewritten(names))}
    with open(a.plan, "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    new = [i for i in items if not i["exists"]]
    upd = [i for i in items if i["exists"] and not i.get("replace")]
    again_items = [i for i in items if i.get("replace")]
    print("=== Preview ===")
    print(f"Library: {plan['library']} ({root})")
    print(f"New files: {len(new)}")
    for i in new:
        print(f"  + {i['rel']}")
    if a.in_place:
        print(f"Overwritten in place (git history keeps the old version): {len(again_items)}")
        for i in again_items:
            print(f"  = {i['rel']}{line_delta(i['target'], i['src'])}")
    else:
        print(f"New versions (old copy goes to {names['archive_dir']}/): {len(upd)}")
        for i in upd:
            what = "old" if i["src"] else "old original, no new copy"
            print(f"  ~ {i['rel']}  {what} -> {names['archive_dir']}/{i['archive_as']}")
    if again_items and not a.in_place:
        print(f"Updated again in this run (its copy from before the run is archived already): {len(again_items)}")
        for i in again_items:
            print(f"  = {i['rel']}")
    if a.confirmed:  # a batch or fast run confirmed at its start: deliver now, in the same call
        print(f"Plan written to {a.plan}. Confirmed at the start of the run: delivering.")
        print()
        finish(a.plan, a.commit, a.class_a_reviewed)
        return
    print(f"Plan written to {a.plan}. Nothing has changed yet.")


def with_related_lists(root, cfg, files, work):
    """files plus the entity pages whose related-files list this delivery changes (entity_pages.py).

    The pages are written into WORK/related/ from the output laid over the library; a page that is
    in the output already is replaced by its refreshed copy."""
    gen = os.path.join(work, "related")
    shutil.rmtree(gen, ignore_errors=True)
    overlay = {r: p for r, p in files if r.endswith(".md")}
    done = dict(entity_pages.refresh_into(root, cfg, overlay, gen))
    out = [(r, done.pop(r, p)) for r, p in files]
    return out + sorted(done.items())


def line_delta(old, new):
    """The " (+a -b lines)" between the current file and its new version, for an in-place preview."""
    try:
        with open(old, encoding="utf-8", errors="replace") as f:
            a = f.read().split("\n")
        with open(new, encoding="utf-8", errors="replace") as f:
            b = f.read().split("\n")
    except OSError:
        return ""
    added = removed = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            removed += i2 - i1
        if op in ("replace", "insert"):
            added += j2 - j1
    return f" (+{added} -{removed} lines)" if added or removed else " (unchanged)"


def stale_originals(root, names, files):
    """Originals in the library that go to the archive folder with this run: those of a topic file that
    gets a new version, and those of a delivered original's topic under another extension. A copy under
    exactly a delivered name is left out here: it is archived as that name's old version. Returns
    [(relative path, None)]."""
    src = names["sources_dir"]
    folder = os.path.join(root, src)
    if not os.path.isdir(folder):
        return []
    rel = {r for r, _ in files}
    updated = {os.path.splitext(r)[0] for r in rel if "/" not in r and r.lower().endswith(".md")
               and os.path.isfile(os.path.join(root, r))}
    delivered = {os.path.splitext(r.split("/", 1)[1])[0] for r in rel if r.startswith(src + "/")}
    out = []
    for name in sorted(os.listdir(folder)):
        r = f"{src}/{name}"
        stem = os.path.splitext(name)[0]
        if r in rel or not os.path.isfile(os.path.join(folder, name)):
            continue
        if stem in updated or stem in delivered:
            out.append((r, None))
    return out


def load_run(path, tz):
    """The run file of a fast intake (package.py --run): the files already archived in this run.
    Started on first use."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if isinstance(run, dict) and isinstance(run.get("archived"), list) and run.get("start"):
            return run
        log.warning("run file %s has no archived list; starting it again", path)
    except FileNotFoundError:
        log.debug("no run file yet at %s: a new run starts", path)
    except (OSError, json.JSONDecodeError) as e:
        log.error("cannot read run file %s: %s", path, e)
        sys.exit(2)
    return {"start": kbconf.now(tz).strftime("%Y%m%d_%H%M%S"), "archived": []}


def save_run(path, run):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)


def rewritten(names):
    """Files every delivery of a fast intake rewrites: archived once per run, then replaced."""
    return {names["index"], names["consolidation_queue"]}


def cmd_deliver(a):
    finish(a.plan, a.commit, a.class_a_reviewed)


def finish(plan_path, title, class_a_reviewed):
    """Deliver the plan; with a title (GitHub backend), commit and push exactly what was written."""
    fail, log_path, written, plan = deliver(plan_path)
    if fail:
        if title:
            print("Not committed: the delivery had failures; fix them and deliver again.")
        sys.exit(3)
    if not title:
        return
    if not plan.get("in_place"):
        print("Not committed: --commit is for a GitHub library (a plan made with --in-place).")
        sys.exit(2)
    paths = os.path.join(os.path.dirname(os.path.abspath(plan_path)), "delivered-paths.txt")
    with open(paths, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(written) + "\n")
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "kbgit.py"), "commit",
           plan["root"], "--title", title, "--paths-file", paths, "--log", log_path]
    cmd += ["--class-a-reviewed"] if class_a_reviewed else []
    print()
    p = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    print(p.stdout.rstrip("\n"))
    if p.returncode:
        print("Delivered into the checkout, but not pushed (see above): the delivery is not complete yet.")
        sys.exit(p.returncode)


def deliver(plan_path):
    """(failures, run log path, relative paths written, plan)."""
    try:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.error("cannot read plan: %s", e)
        sys.exit(2)
    arch = plan["archive_dir"]
    os.makedirs(arch, exist_ok=True)
    lines = ["=== Delivery ===", f"Library: {plan['library']}", f"Time: {plan['base_time']}", ""]
    ok = fail = 0
    archived, written = [], []
    for i in plan["items"]:
        target, rel = i["target"], i["rel"]
        try:
            if i["src"] and (not os.path.isfile(i["src"]) or os.path.getsize(i["src"]) != i["src_size"]):
                raise RuntimeError("output file changed after preview")
            if i["exists"]:
                if not os.path.isfile(target):
                    raise RuntimeError("target disappeared after preview")
                st = os.stat(target)
                if st.st_size != i["old_size"] or st.st_mtime != i["old_mtime"]:
                    raise RuntimeError("target changed after preview")
            if i.get("replace"):
                shutil.copy2(i["src"], target)
                lines.append(f"  update  | {rel}" if plan.get("in_place") else
                             f"  update  | {rel} (archived earlier in this run)")
                written.append(rel)
                ok += 1
                continue
            if i["exists"]:
                dst = os.path.join(arch, i["archive_as"])
                if os.path.exists(dst):
                    raise RuntimeError(f"archive name already used: {i['archive_as']}")
                shutil.move(target, dst)
                lines.append(f"  archive | {rel} -> {i['archive_as']}")
                if rel in plan.get("rewritten", ()):
                    archived.append(rel)
            elif os.path.exists(target):
                raise RuntimeError("a file with this name appeared after preview")
            if not i["src"]:  # an old original whose topic file moved on: archived only
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(i["src"], target)
            lines.append(f"  write   | {rel}")
            written.append(rel)
            if not i["exists"] and rel in plan.get("rewritten", ()):
                archived.append(rel)  # new in this run: there is no earlier copy to keep
            ok += 1
        except (OSError, RuntimeError) as e:
            fail += 1
            lines.append(f"  failed  | {rel} | {e}")
            log.error("%s: %s", rel, e)
    end = kbconf.now(plan["timezone"]).strftime("%Y%m%d_%H%M%S")
    lines += ["", f"Written {ok}, failed {fail}.", "", "=== End ==="]
    if plan.get("run"):  # a fast intake: one readme and one run log per run, appended to
        end = plan["run_start"]
        run = load_run(plan["run"], plan["timezone"])
        run["archived"] = sorted(set(run["archived"]) | set(archived))
        save_run(plan["run"], run)
    mode = "a" if plan.get("run") else "w"
    if os.path.isfile(plan["readme"]):
        with open(plan["readme"], encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(arch, f"_delivery_{end}_README.txt"), mode, encoding="utf-8", newline="\n") as f:
            f.write(text.rstrip("\n") + "\n\n")
    log_name = f"{plan['log_prefix']}{end}.txt"
    with open(os.path.join(arch, log_name), mode, encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if plan.get("in_place"):
        print(f"Run log (work folder, not in the library): {os.path.join(arch, log_name)}")
    else:
        print(f"Run log: {os.path.basename(arch)}/{log_name}")
    return fail, os.path.join(arch, log_name), written, plan


def main():
    ap = argparse.ArgumentParser(description="Check and deliver intake output")
    kbconf.add_log_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview"); p.add_argument("out"); p.add_argument("--library", required=True)
    p.add_argument("--plan", required=True); p.add_argument("--max-name-len", type=int, default=0)
    p.add_argument("--run", help="run file of a fast intake (work folder): the index and the queue are "
                   "archived once per run, and the readme and run log are one file per run")
    p.add_argument("--in-place", action="store_true",
                   help="GitHub backend: overwrite existing files in place, keep the run log in the work folder")
    p.add_argument("--confirmed", action="store_true",
                   help="the run was confirmed at its start (batch or fast intake): deliver in the same call")
    p.add_argument("--commit", metavar="TITLE", help="GitHub backend, with --confirmed: commit and push after delivery")
    p.add_argument("--class-a-reviewed", action="store_true",
                   help="the user confirmed that every class-A candidate is not class-A data")
    p = sub.add_parser("deliver"); p.add_argument("--plan", required=True)
    p.add_argument("--commit", metavar="TITLE", help="GitHub backend: commit and push what was written")
    p.add_argument("--class-a-reviewed", action="store_true", help="passed on to kbgit.py commit")
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    log.info("subcommand: %s", a.cmd)
    {"preview": cmd_preview, "deliver": cmd_deliver}[a.cmd](a)


if __name__ == "__main__":
    main()
