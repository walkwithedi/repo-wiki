#!/usr/bin/env python3
"""Git steps of a GitHub library (references/backend-github.md), one call each.

  sync ROOT [--read-only]
      Brings the checkout up to date: git fetch of the remote's default branch (git ls-remote --symref
      origin HEAD, else main), then a fast-forward when the branch is only behind. A checkout on another
      branch (a cloud session checks out a branch of its own) is first switched to the default branch,
      when no tracked file has uncommitted changes and the branch holds no commit the default branch
      lacks; otherwise it says why it stays. Prints one status line per step. --read-only (kb-query)
      never stops: when the remote cannot be reached, the branch has diverged or cannot be switched, it
      says so and the local copy is used. Without --read-only those cases exit 3 (diverged, local changes
      in the way, another branch) or 4 (remote unreachable), and nothing is written to the library.
  commit ROOT --title TITLE (--path P ... | --paths-file FILE) [--log FILE] [--author "Name <email>"]
         [--allow-instructions] [--class-a-reviewed]
      One commit for one delivery round, pushed to the current branch:
      1. stages exactly the given paths (new, changed, moved or removed) and refuses when anything
         else is staged, or when a path is a repository file (README.md, CLAUDE.md, AGENTS.md, names
         starting with a dot; --allow-instructions lets CLAUDE.md and AGENTS.md through for init);
      2. with sensitivity enabled in _kb.json, scans the added lines and the message for class-A data
         (kbconf.py scan-a) and refuses on a hit, unless --class-a-reviewed says the user checked them;
      3. commits with the identity the repository's own instructions name (a "Name <email>" on a line
         of CLAUDE.md or AGENTS.md that mentions the author or the identity), else --author, else git's
         configured one; the message is the title, a blank line and the run log lines, without
         assistant trailers (Co-Authored-By, session links, "Generated with");
      4. git pull --rebase, then git push to the default branch, retrying network errors after 2, 4, 8
         and 16 seconds; a push rejected because another session pushed first pulls and pushes again,
         up to 3 times. Refuses to commit on any other branch (run sync first).
      Prints the short hash. A rebase conflict is aborted and exits 3 with the conflicting files; the
      commit stays local (see drop-local).
  drop-local ROOT [--yes]
      Lists the commits not on the remote. With --yes, only after the user confirmed that they are to
      be dropped: git reset --keep to the remote branch, so the round can be redone on the current
      library. The dropped hashes are printed (git reflog keeps them for a while).

Only the standard library and the git command. stdout: results. stderr: log.
Exit codes: 0 ok; 2 bad arguments, not a git checkout; 3 refused or a conflict; 4 remote unreachable;
5 committed locally but not pushed.
"""
import argparse
import logging
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbconf  # noqa: E402

log = logging.getLogger("kbgit")
REPO_FILES = {"README.md", "CLAUDE.md", "AGENTS.md"}
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")
IDENTITY_LINE = re.compile(r"author|identity|作者|身份", re.I)
IDENTITY = re.compile(r"([^<>:：;；,，`*|]+?)\s*<([^<>\s@]+@[^<>\s]+)>")
TRAILER = re.compile(r"^\s*(co-authored-by:|claude-session:|.*generated with \[?claude)", re.I)
REJECTED = re.compile(r"\[rejected\]|non-fast-forward|fetch first|failed to push some refs", re.I)
PUSH_TRIES = 3
NETWORK = re.compile(r"could not resolve|unable to access|connection|timed out|early eof|rpc failed|"
                     r"remote end hung up|\b50[234]\b|temporary failure|network", re.I)


class GitError(Exception):
    def __init__(self, msg, code=3):
        super().__init__(msg)
        self.code = code


def delays():
    raw = os.environ.get("KBGIT_RETRY_DELAYS")  # tests shorten the waits
    return [float(x) for x in raw.split(",") if x] if raw is not None else [2, 4, 8, 16]


def git(root, *args, check=True, stdin=None, env=None):
    cmd = ["git", "-C", root, "-c", "core.quotepath=false", *args]
    log.debug("run: %s", " ".join(cmd))
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if check and p.returncode:
        raise GitError(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()}")
    return p


def with_retry(root, *args):
    """A network command, retried on network errors only."""
    waits = delays()
    for attempt in range(len(waits) + 1):
        p = git(root, *args, check=False)
        if not p.returncode:
            return p
        msg = (p.stderr or p.stdout).strip()
        if not NETWORK.search(msg) or attempt == len(waits):
            return p
        log.warning("git %s failed (%s); retrying in %ss", args[0], msg.splitlines()[-1] if msg else "", waits[attempt])
        time.sleep(waits[attempt])
    return p


def top(root):
    p = git(root, "rev-parse", "--show-toplevel", check=False)
    if p.returncode:
        raise GitError(f"not a git checkout: {root}", 2)
    return p.stdout.strip()


def branch(root):
    p = git(root, "symbolic-ref", "--short", "HEAD", check=False)
    if p.returncode:
        raise GitError("HEAD is detached; check out the default branch first")
    return p.stdout.strip()


def has_origin(root):
    return not git(root, "remote", "get-url", "origin", check=False).returncode


def counts(root, br):
    """(ahead, behind) of the branch against origin/<branch>; None when there is no such ref."""
    p = git(root, "rev-list", "--left-right", "--count", f"HEAD...origin/{br}", check=False)
    if p.returncode:
        return None
    ahead, behind = p.stdout.split()
    return int(ahead), int(behind)


def short(root, rev="HEAD"):
    return git(root, "rev-parse", "--short", rev).stdout.strip()


def current_branch(root):
    """The checked-out branch, or None when HEAD is detached."""
    p = git(root, "symbolic-ref", "--short", "HEAD", check=False)
    return p.stdout.strip() if not p.returncode else None


def default_branch(root, ask_remote=True):
    """The remote's default branch: git ls-remote --symref origin HEAD (cached as origin/HEAD), else the
    cached origin/HEAD, else main. ask_remote=False uses the cache when there is one."""
    p = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    cached = p.stdout.strip()[len("origin/"):] if not p.returncode and p.stdout.strip().startswith("origin/") else ""
    if cached and not ask_remote:
        return cached
    p = with_retry(root, "ls-remote", "--symref", "origin", "HEAD")
    m = re.search(r"^ref:\s*refs/heads/(\S+)\s+HEAD$", p.stdout, re.M) if not p.returncode else None
    if m:
        br = m.group(1)
        git(root, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{br}", check=False)
        log.info("default branch from the remote: %s", br)
        return br
    log.info("the remote did not name its default branch; using %s", cached or "main")
    return cached or "main"


def switch_to(root, cur, br):
    """Switch a checkout on another branch (or a detached HEAD) to br. Returns (ok, message)."""
    if not git(root, "rev-parse", "--verify", "-q", f"origin/{br}", check=False).stdout.strip():
        return False, f"origin/{br} not found"
    dirty = [ln for ln in git(root, "status", "--porcelain", "--untracked-files=no").stdout.splitlines() if ln.strip()]
    if dirty:
        return False, "tracked files have uncommitted changes: " + ", ".join(ln[3:] for ln in dirty[:10])
    local = bool(git(root, "rev-parse", "--verify", "-q", f"refs/heads/{br}", check=False).stdout.strip())
    exclude = [f"origin/{br}"] + ([br] if local else [])
    own = [x for x in git(root, "rev-list", "HEAD", "--not", *exclude).stdout.split() if x]
    if own:
        return False, f"{len(own)} commit(s) on {cur or 'the detached HEAD'} are not on {br}"
    args = ("switch", "-q", br) if local else ("switch", "-q", "-c", br, "--track", f"origin/{br}")
    p = git(root, *args, check=False)
    if p.returncode:
        return False, (p.stderr or p.stdout).strip().splitlines()[-1]
    git(root, "branch", "-q", f"--set-upstream-to=origin/{br}", br, check=False)
    return True, f"switched from {cur or 'a detached HEAD'} to {br}"


# ---------- sync ----------

def cmd_sync(a):
    root = top(a.root)
    if not has_origin(root):
        print(f"no remote: using the local copy at {short(root)}")
        return 0
    br = default_branch(root)
    cur = current_branch(root)
    p = with_retry(root, "fetch", "origin", f"+refs/heads/{br}:refs/remotes/origin/{br}")
    if p.returncode:
        msg = (p.stderr or p.stdout).strip().splitlines()
        print(f"fetch failed ({msg[-1] if msg else 'no message'}); the local copy at {short(root)} may not be current")
        return 0 if a.read_only else 4
    if cur != br:
        ok, msg = switch_to(root, cur, br)
        if not ok:
            print(f"stays on {cur or 'a detached HEAD'}, not the default branch {br}: {msg}. "
                  + ("Using the local copy, which may not be current." if a.read_only else
                     "Stop: report it; library changes are committed on the default branch only."))
            return 0 if a.read_only else 3
        print(msg)
    c = counts(root, br)
    if c is None:
        print(f"origin/{br} not found; using the local copy at {short(root)}")
        return 0
    ahead, behind = c
    if ahead and behind:
        print(f"diverged: {ahead} local commit(s) not on origin/{br} and {behind} new there. "
              + ("Using the local copy." if a.read_only else
                 "Stop: report it; kbgit.py drop-local lists the local commits."))
        return 0 if a.read_only else 3
    if behind:
        p = git(root, "merge", "--ff-only", f"origin/{br}", check=False)
        if p.returncode:
            print(f"cannot fast-forward ({(p.stderr or p.stdout).strip().splitlines()[-1]}); "
                  + ("using the local copy, which is behind." if a.read_only else "stop and report git's message."))
            return 0 if a.read_only else 3
        print(f"updated: {behind} new commit(s), now at {short(root)}")
        return 0
    if ahead:
        print(f"up to date, with {ahead} local commit(s) not pushed yet (the next commit pushes them)")
        return 0
    print(f"up to date at {short(root)}")
    return 0


# ---------- commit ----------

def identity_from_instructions(root):
    for name in INSTRUCTION_FILES:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if IDENTITY_LINE.search(line):
                    m = IDENTITY.search(line)
                    if m and m.group(1).strip(" -*·"):
                        return m.group(1).strip(" -*·"), m.group(2), name
    return None


def identity(root, author):
    if author:
        m = IDENTITY.fullmatch(author.strip())
        if not m:
            raise GitError(f'--author must look like "Name <email>": {author}', 2)
        return m.group(1).strip(), m.group(2), "--author"
    found = identity_from_instructions(root)
    if found:
        return found
    name = git(root, "config", "user.name", check=False).stdout.strip()
    email = git(root, "config", "user.email", check=False).stdout.strip()
    if not (name and email):
        raise GitError("no commit identity: the repository instructions name none and git has none configured")
    return name, email, "git config"


def norm_paths(root, paths, allow_instructions):
    out, bad = [], []
    for p in paths:
        p = p.strip().replace("\\", "/")
        if not p:
            continue
        full = os.path.normpath(os.path.join(root, p))
        if os.path.isabs(p) or not (full == root or full.startswith(root + os.sep)):
            bad.append(f"outside the library: {p}")
            continue
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        parts = rel.split("/")
        if any(x.startswith(".") for x in parts) or (len(parts) == 1 and parts[0] in REPO_FILES
                                                      and not (allow_instructions and parts[0] in INSTRUCTION_FILES)):
            bad.append(f"repository file, never committed by the skills: {rel}")
            continue
        out.append(rel)
    return list(dict.fromkeys(out)), bad


def within(path, paths):
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths)


def staged(root):
    p = git(root, "diff", "--cached", "--name-only", "-z")
    return [x for x in p.stdout.split("\0") if x]


def message(title, log_path):
    lines = [title.strip(), ""]
    if log_path:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for ln in f.read().replace("\r\n", "\n").split("\n"):
                if ln.startswith("===") or TRAILER.match(ln):
                    continue
                lines.append(ln.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def sensitivity(root):
    try:
        cfg = kbconf.load_library(root)
    except kbconf.ConfigError:
        return None
    s = cfg.get("sensitivity") or {}
    return int(s.get("keep_last", 4)) if s.get("enabled") else None


def added_lines(root):
    p = git(root, "diff", "--cached", "-U0", "--no-color")
    out, path = [], ""
    for ln in p.stdout.split("\n"):
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else ln[4:]
        elif ln.startswith("+") and not ln.startswith("+++"):
            out.append((path, ln[1:]))
    return out


def cmd_commit(a):
    root = top(a.root)
    br = branch(root)
    if has_origin(root):
        want = default_branch(root, ask_remote=False)
        if br != want:
            print(f"refused: the checkout is on {br}, not the default branch {want}; run kbgit.py sync first. "
                  "Nothing is committed.")
            return 3
    paths = list(a.path or [])
    if a.paths_file:
        with open(a.paths_file, encoding="utf-8") as f:
            paths += f.read().split("\n")
    paths, bad = norm_paths(root, paths, a.allow_instructions)
    for b in bad:
        print(f"refused: {b}")
    if bad:
        return 3
    if not paths:
        print("refused: no paths given")
        return 2
    before = [x for x in staged(root) if not within(x, paths)]  # a git mv of this round is staged already
    if before:
        print("refused: changes are staged already, outside this round: " + ", ".join(before[:20]))
        return 3
    present = []
    for rel in paths:
        if os.path.exists(os.path.join(root, rel)) or git(root, "ls-files", "--", rel).stdout.strip():
            present.append(rel)
        else:
            log.warning("skipped, neither in the checkout nor tracked: %s", rel)
    if present:
        git(root, "add", "-A", "--", *present)
    now = staged(root)
    outside = [x for x in now if not within(x, paths)]
    if outside:
        git(root, "reset", "-q", "--", *now)
        print("refused: staging picked up other files: " + ", ".join(outside[:20]))
        return 3
    if not now:
        print("nothing to commit: the paths have no changes")
        return 0
    msg = message(a.title, a.log)
    keep = sensitivity(root)
    if keep is not None and not a.class_a_reviewed:
        hits = [(path, kind, v) for path, ln in added_lines(root) for _, kind, v in kbconf.scan_class_a(ln, keep)]
        hits += [("commit message", kind, v) for _, kind, v in kbconf.scan_class_a(msg, keep)]
        if hits:
            git(root, "reset", "-q", "--", *now)
            for path, kind, v in hits[:30]:
                print(f"class-A candidate: {path}: {kind}: {v}")
            print(f"refused: {len(hits)} class-A candidate(s); mask them and deliver again, or, when the user "
                  "confirmed each is not class-A data, run again with --class-a-reviewed. Nothing is committed.")
            return 3
    name, email, source = identity(root, a.author)
    who = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
               GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)  # over any identity in the environment
    git(root, "commit", "-q", "-F", "-", stdin=msg, env=who)
    head = short(root)
    print(f"committed: {head} ({len(now)} file(s)) as {name} <{email}> (from {source})")
    if not has_origin(root):
        print("not pushed: the checkout has no remote")
        return 5
    for attempt in range(1, PUSH_TRIES + 1):
        p = with_retry(root, "pull", "--rebase", "origin", br)
        if p.returncode:
            conflicts = git(root, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            if os.path.isdir(os.path.join(root, ".git", "rebase-merge")) or os.path.isdir(os.path.join(root, ".git", "rebase-apply")):
                git(root, "rebase", "--abort", check=False)
                print("conflict with newer commits on the remote in: " + (", ".join(conflicts) or "(see git's message)"))
                print(f"the commit {head} stays local and is not pushed. Report it; after the user confirms, "
                      "kbgit.py drop-local ROOT --yes and redo this round on the current library.")
                return 3
            msg_ = (p.stderr or p.stdout).strip().splitlines()
            print(f"not pushed: git pull failed ({msg_[-1] if msg_ else 'no message'}); the commit {head} is local only")
            return 5 if not NETWORK.search(p.stderr or "") else 4
        head = short(root)
        p = with_retry(root, "push", "origin", f"HEAD:{br}")
        if not p.returncode:
            print(f"pushed: {head} to origin/{br}")
            return 0
        msg = (p.stderr or p.stdout).strip()
        if not REJECTED.search(msg) or attempt == PUSH_TRIES:
            break
        log.warning("push rejected, another session pushed first; pulling again (try %d of %d)", attempt + 1, PUSH_TRIES)
    msg_ = (p.stderr or p.stdout).strip().splitlines()
    print(f"not pushed: {msg_[-1] if msg_ else 'git push failed'}; the commit {head} is local only")
    return 5


# ---------- drop-local ----------

def cmd_drop_local(a):
    root = top(a.root)
    br = branch(root)
    if not git(root, "rev-parse", "--verify", "-q", f"origin/{br}", check=False).stdout.strip():
        print(f"refused: origin/{br} not found")
        return 3
    p = git(root, "log", f"origin/{br}..HEAD", "--format=%h %ad %s", "--date=short")
    commits = [x for x in p.stdout.split("\n") if x]
    if not commits:
        print("no local commits to drop")
        return 0
    print(f"local commits not on origin/{br}:")
    for c in commits:
        print(f"  {c}")
    if not a.yes:
        print("nothing changed; with the user's confirmation run again with --yes")
        return 0
    p = git(root, "reset", "--keep", f"origin/{br}", check=False)
    if p.returncode:
        print(f"refused: {(p.stderr or p.stdout).strip()}")
        return 3
    print(f"dropped {len(commits)} commit(s); now at {short(root)} (git reflog keeps them for a while)")
    return 0


def main():
    kbconf.utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    kbconf.add_log_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync"); p.add_argument("root")
    p.add_argument("--read-only", action="store_true", help="kb-query: never stop, use the local copy")
    p = sub.add_parser("commit"); p.add_argument("root")
    p.add_argument("--title", required=True, help='first line, e.g. "Intake: 3 files"')
    p.add_argument("--path", action="append", help="a path this round wrote, moved or removed (repeatable)")
    p.add_argument("--paths-file", help="file with one path per line")
    p.add_argument("--log", help="run log whose lines form the message body")
    p.add_argument("--author", help='"Name <email>", when the repository instructions name none')
    p.add_argument("--allow-instructions", action="store_true", help="init: CLAUDE.md and AGENTS.md may be committed")
    p.add_argument("--class-a-reviewed", action="store_true", help="the user checked every class-A candidate")
    p = sub.add_parser("drop-local"); p.add_argument("root")
    p.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    kbconf.setup_logging(a.log_level)
    try:
        return {"sync": cmd_sync, "commit": cmd_commit, "drop-local": cmd_drop_local}[a.cmd](a)
    except GitError as e:
        print(f"error: {e}")
        return e.code
    except OSError as e:
        print(f"error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
