"""Tests for the GitHub backend scripts (kbgit.py, package.py --commit). Standard library and git only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "kb-ingest", "scripts")
sys.path.insert(0, SCRIPTS)
import kbconf  # noqa: E402

ENV = dict(os.environ, KBGIT_RETRY_DELAYS="", GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Someone", GIT_AUTHOR_EMAIL="someone@users.noreply.github.com",
           GIT_COMMITTER_NAME="Someone", GIT_COMMITTER_EMAIL="someone@users.noreply.github.com")
IDENTITY_LINE = "- 提交作者用仓库所有者身份：Zhang San <zhangsan@users.noreply.github.com>；提交说明用中文。\n"


def run(script, *args, check=True, cwd=None):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True,
                       encoding="utf-8", env=ENV, cwd=cwd)
    if check and p.returncode != 0:
        raise AssertionError(f"{script} {args} exited {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=ENV)
    if p.returncode:
        raise AssertionError(f"git {args}: {p.stderr}")
    return p.stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def card_number(prefix="6222" + "0" * 14):
    return next(prefix + d for d in "0123456789" if kbconf.luhn_ok(prefix + d))


@unittest.skipUnless(shutil.which("git"), "git not installed")
class Repo(unittest.TestCase):
    """A bare origin and two clones of one library (two windows, or another session)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        d = self._t.name
        self.origin = os.path.join(d, "origin.git")
        git(d, "init", "-q", "--bare", "-b", "main", self.origin)
        self.a = os.path.join(d, "a")
        git(d, "clone", "-q", self.origin, self.a)
        git(self.a, "checkout", "-q", "-b", "main")
        write(os.path.join(self.a, "CLAUDE.md"), "# Library\n\n" + IDENTITY_LINE)
        write(os.path.join(self.a, "_kb.json"), json.dumps({"schema": 1, "label": "Life", "timezone": "UTC",
                                                            "sensitivity": {"enabled": True, "keep_last": 4}}))
        write(os.path.join(self.a, "00_Spec.md"), "# Spec\n")
        git(self.a, "add", ".")
        git(self.a, "commit", "-q", "-m", "start")
        git(self.a, "push", "-q", "-u", "origin", "main")
        self.b = os.path.join(d, "b")
        git(d, "clone", "-q", self.origin, self.b)
        self.d = d

    def tearDown(self):
        self._t.cleanup()

    def last(self, repo, fmt):
        return git(repo, "log", "-1", f"--format={fmt}").strip()


class KbgitCommitTest(Repo):
    def test_rebase_conflict_in_worktree_is_aborted(self):
        wt = os.path.join(self.d, "wt")
        git(self.a, "switch", "-q", "-c", "parking")
        git(self.a, "worktree", "add", "-q", wt, "main")
        write(os.path.join(self.b, "00_Spec.md"), "remote change\n")
        git(self.b, "add", "00_Spec.md")
        git(self.b, "commit", "-qm", "remote")
        git(self.b, "push", "-q", "origin", "main")
        write(os.path.join(wt, "00_Spec.md"), "local change\n")
        p = run("kbgit.py", "commit", wt, "--title", "update", "--path", "00_Spec.md", check=False)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("conflict with newer commits", p.stdout)
        self.assertEqual(git(wt, "branch", "--show-current").strip(), "main")
        self.assertEqual(git(wt, "status", "--porcelain").strip(), "")

    def test_identity_message_and_push(self):
        write(os.path.join(self.a, "02_Health_Report_A.md"), "report\n")
        write(os.path.join(self.d, "log.txt"), "=== Delivery ===\n  write   | 02_Health_Report_A.md\n\nWritten 1.\n"
              "=== End ===\nCo-Authored-By: Bot <bot@users.noreply.github.com>\n")
        out = run("kbgit.py", "commit", self.a, "--title", "入库：1 个文件", "--path", "02_Health_Report_A.md",
                  "--log", os.path.join(self.d, "log.txt")).stdout
        self.assertIn("as Zhang San <zhangsan@users.noreply.github.com> (from CLAUDE.md)", out)
        self.assertIn("pushed: ", out)
        self.assertEqual(self.last(self.a, "%an <%ae>|%cn"), "Zhang San <zhangsan@users.noreply.github.com>|Zhang San")
        body = self.last(self.a, "%B")
        self.assertTrue(body.startswith("入库：1 个文件\n\n  write   | 02_Health_Report_A.md"))
        self.assertNotIn("Co-Authored-By", body)
        self.assertNotIn("===", body)
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.a, "rev-parse", "HEAD"))

    def test_refuses_repository_files_and_other_staged_changes(self):
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "CLAUDE.md", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("repository file", p.stdout)
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", ".claude/x", check=False)
        self.assertEqual(p.returncode, 3)
        write(os.path.join(self.a, "02_Other.md"), "other\n")
        git(self.a, "add", "02_Other.md")
        write(os.path.join(self.a, "02_Mine.md"), "mine\n")
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_Mine.md", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("staged already, outside this round: 02_Other.md", p.stdout)

    def test_staged_move_of_this_round_is_committed(self):
        write(os.path.join(self.a, "Notes", "n1.md"), "note\n")
        run("kbgit.py", "commit", self.a, "--title", "Quick note", "--path", "Notes/n1.md")
        os.makedirs(os.path.join(self.a, "Notes", "Filed"))
        git(self.a, "mv", "Notes/n1.md", "Notes/Filed/n1.md")
        run("kbgit.py", "commit", self.a, "--title", "Notes filed", "--path", "Notes/n1.md",
            "--path", "Notes/Filed/n1.md")
        self.assertEqual(self.last(self.a, "%s"), "Notes filed")
        self.assertEqual(git(self.a, "status", "--porcelain").strip(), "")

    def test_class_a_refused_then_reviewed(self):
        write(os.path.join(self.a, "02_Money.md"), f"order {card_number()}\n")
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_Money.md", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("class-A candidate: 02_Money.md: card number: ", p.stdout)
        self.assertNotIn(card_number(), p.stdout)
        self.assertEqual(git(self.a, "diff", "--cached", "--name-only").strip(), "")  # unstaged again
        run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_Money.md", "--class-a-reviewed")

    def test_other_window_pushed_first(self):
        write(os.path.join(self.b, "Notes", "from-b.md"), "b\n")
        git(self.b, "add", ".")
        git(self.b, "commit", "-q", "-m", "b")
        git(self.b, "push", "-q", "origin", "main")
        write(os.path.join(self.a, "02_A.md"), "a\n")
        out = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_A.md").stdout
        self.assertIn("pushed: ", out)
        self.assertTrue(os.path.isfile(os.path.join(self.a, "Notes", "from-b.md")))

    def test_conflict_keeps_commit_local_and_drop_local(self):
        write(os.path.join(self.b, "00_Spec.md"), "# Spec\nfrom b\n")
        git(self.b, "commit", "-qam", "b")
        git(self.b, "push", "-q", "origin", "main")
        write(os.path.join(self.a, "00_Spec.md"), "# Spec\nfrom a\n")
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "00_Spec.md", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("conflict with newer commits on the remote in: 00_Spec.md", p.stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.a, ".git", "rebase-merge")))
        out = run("kbgit.py", "drop-local", self.a).stdout
        self.assertIn("local commits not on origin/main", out)
        self.assertIn("nothing changed", out)
        run("kbgit.py", "drop-local", self.a, "--yes")
        with open(os.path.join(self.a, "00_Spec.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Spec\nfrom b\n")


class KbgitSyncTest(Repo):
    def test_behind_ahead_and_diverged(self):
        self.assertIn("up to date at", run("kbgit.py", "sync", self.b).stdout)
        write(os.path.join(self.a, "02_A.md"), "a\n")
        run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_A.md")
        self.assertIn("updated: 1 new commit(s)", run("kbgit.py", "sync", self.b).stdout)
        write(os.path.join(self.b, "02_B.md"), "b\n")
        git(self.b, "add", ".")
        git(self.b, "commit", "-qm", "b")
        self.assertIn("1 local commit(s) not pushed", run("kbgit.py", "sync", self.b).stdout)
        write(os.path.join(self.a, "02_C.md"), "c\n")
        run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_C.md")
        p = run("kbgit.py", "sync", self.b, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("diverged", p.stdout)
        p = run("kbgit.py", "sync", self.b, "--read-only")
        self.assertIn("Using the local copy.", p.stdout)

    def test_shallow_clone_behind_is_not_diverged(self):
        c = os.path.join(self.d, "c")
        git(self.d, "clone", "-q", "--depth", "1", "file://" + self.origin, c)
        for name in ("02_A.md", "02_B.md", "02_C.md"):
            write(os.path.join(self.a, name), "x\n")
            run("kbgit.py", "commit", self.a, "--title", "x", "--path", name)
        git(c, "fetch", "-q", "--depth", "1", "origin", "+main:refs/remotes/origin/main")
        self.assertNotEqual(subprocess.run(["git", "merge-base", "HEAD", "origin/main"], cwd=c,
                                           capture_output=True, env=ENV).returncode, 0)
        out = run("kbgit.py", "sync", c).stdout
        self.assertIn("shallow clone: fetched more history", out)
        self.assertIn("updated: 3 new commit(s)", out)
        self.assertTrue(os.path.isfile(os.path.join(c, "02_C.md")))

    def test_unreachable_remote(self):
        git(self.b, "remote", "set-url", "origin", os.path.join(self.d, "gone.git"))
        p = run("kbgit.py", "sync", self.b, check=False)
        self.assertEqual(p.returncode, 4)
        self.assertIn("fetch failed", p.stdout)
        self.assertEqual(run("kbgit.py", "sync", self.b, "--read-only").returncode, 0)


class KbgitBranchTest(Repo):
    """A cloud session checks the library out on a branch of its own, which the remote does not have."""

    def session_branch(self, repo, drop_main=False):
        git(repo, "checkout", "-q", "-b", "claude/session-x")
        if drop_main:
            git(repo, "branch", "-q", "-D", "main")

    def test_sync_switches_to_the_default_branch(self):
        self.session_branch(self.b, drop_main=True)
        write(os.path.join(self.a, "02_A.md"), "a\n")
        run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_A.md")
        out = run("kbgit.py", "sync", self.b).stdout
        self.assertIn("switched from claude/session-x to main", out)
        self.assertIn("up to date at", out)  # main is new, made from the fetched origin/main
        self.assertTrue(os.path.isfile(os.path.join(self.b, "02_A.md")))
        self.assertEqual(git(self.b, "branch", "--show-current").strip(), "main")
        self.assertEqual(git(self.b, "rev-parse", "--abbrev-ref", "main@{upstream}").strip(), "origin/main")
        write(os.path.join(self.b, "02_B.md"), "b\n")
        self.assertIn("pushed: ", run("kbgit.py", "commit", self.b, "--title", "x", "--path", "02_B.md").stdout)
        self.assertEqual(git(self.origin, "branch", "--format=%(refname:short)").split(), ["main"])

    def test_read_only_sync_switches_and_fast_forwards(self):
        self.session_branch(self.b)  # the local main stays behind
        write(os.path.join(self.a, "02_A.md"), "a\n")
        run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_A.md")
        out = run("kbgit.py", "sync", self.b, "--read-only").stdout
        self.assertIn("switched from claude/session-x to main", out)
        self.assertIn("updated: 1 new commit(s)", out)

    def test_stays_on_a_branch_with_its_own_commits_or_changes(self):
        self.session_branch(self.b)
        write(os.path.join(self.b, "00_Spec.md"), "# Spec\nchanged\n")
        p = run("kbgit.py", "sync", self.b, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("uncommitted changes: 00_Spec.md", p.stdout)
        git(self.b, "commit", "-qam", "own")
        p = run("kbgit.py", "sync", self.b, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("1 commit(s) on claude/session-x are not on main", p.stdout)
        p = run("kbgit.py", "sync", self.b, "--read-only")
        self.assertIn("Using the local copy, which may not be current.", p.stdout)
        self.assertEqual(git(self.b, "branch", "--show-current").strip(), "claude/session-x")

    def test_commit_refused_off_the_default_branch(self):
        self.session_branch(self.b)
        write(os.path.join(self.b, "02_B.md"), "b\n")
        p = run("kbgit.py", "commit", self.b, "--title", "x", "--path", "02_B.md", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("not the default branch main; run kbgit.py sync first", p.stdout)
        self.assertEqual(git(self.b, "status", "--porcelain").strip(), "?? 02_B.md")

    def test_default_branch_named_by_the_remote(self):
        git(self.a, "push", "-q", "origin", "main:trunk")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/trunk")
        out = run("kbgit.py", "sync", self.b).stdout
        self.assertIn("switched from main to trunk", out)

    def test_push_rejected_once_is_pulled_and_pushed_again(self):
        mark = os.path.join(self.d, "rejected-once")
        hook = os.path.join(self.origin, "hooks", "pre-receive")
        write(hook, f'#!/bin/sh\nif [ ! -f "{mark}" ]; then touch "{mark}"; echo busy >&2; exit 1; fi\nexit 0\n')
        os.chmod(hook, 0o755)
        write(os.path.join(self.a, "02_A.md"), "a\n")
        p = run("kbgit.py", "commit", self.a, "--title", "x", "--path", "02_A.md")
        self.assertIn("pushed: ", p.stdout)
        self.assertIn("push rejected", p.stderr)
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.a, "rev-parse", "HEAD"))


QUERY = os.path.join(ROOT, "skills", "kb-query", "scripts", "kbfind.py")


class KbfindHistoryTest(Repo):
    def test_versions_wording_and_old_version(self):
        card = os.path.join(self.a, "00_Status-Card.md")
        for text in ("# Card\n\n1. Window closes at 17:00\n", "# Card\n\n1. Window closes at 18:00\n"):
            write(card, text)
            run("kbgit.py", "commit", self.a, "--title", "Consolidation: 1 file", "--path", "00_Status-Card.md")
        first = git(self.a, "log", "--format=%h", "--reverse", "--", "00_Status-Card.md").split()[0]
        p = subprocess.run([sys.executable, QUERY, "history", self.a, "00_Status-Card.md", "--words", "17:00"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("00_Status-Card.md: 2 version(s)", p.stdout)
        self.assertIn('commits where "17:00" appeared or vanished: 2', p.stdout)
        p = subprocess.run([sys.executable, QUERY, "history", self.a, "00_Status-Card.md", "--at", first,
                            "--words", "Window"], capture_output=True, text=True, encoding="utf-8")
        self.assertIn(f"00_Status-Card.md as of {first}", p.stdout)
        self.assertIn("1. Window closes at 17:00", p.stdout)
        p = subprocess.run([sys.executable, QUERY, "history", self.a, "CLAUDE.md"], capture_output=True, text=True,
                           encoding="utf-8")
        self.assertIn("not a knowledge file", p.stdout)


NOTE = os.path.join(ROOT, "skills", "kb-note", "scripts", "note.py")


class NoteTest(Repo):
    def save(self, topic, body, check=True):
        write(os.path.join(self.d, "note.txt"), body)
        p = subprocess.run([sys.executable, NOTE, "save", self.a, "--topic", topic, "--body",
                            os.path.join(self.d, "note.txt")], capture_output=True, text=True, encoding="utf-8", env=ENV)
        if check:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def test_save_name_push_and_backlog(self):
        out = self.save("周五前发 方案/初稿！", "Quick note\nWords: x\n").stdout
        self.assertRegex(out, r"written: Quick-Notes/\d{8}-\d{4}_周五前发-方案-初稿\.md \(notes folder created\)")
        self.assertIn("pushed: ", out)
        self.assertIn("backlog: 1 note(s) waiting, oldest ", out)
        self.assertTrue(self.last(self.a, "%s").startswith("Quick note: "))
        self.assertEqual(self.last(self.a, "%an"), "Zhang San")
        out = self.save("周五前发 方案/初稿！", "second\n").stdout  # same minute, same topic
        self.assertRegex(out, r"written: Quick-Notes/\d{8}-\d{4}-2_周五前发-方案-初稿\.md")
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.a, "rev-parse", "HEAD"))

    def test_syncs_first_from_a_session_branch(self):
        git(self.a, "checkout", "-q", "-b", "claude/session-x")
        write(os.path.join(self.b, "02_B.md"), "b\n")
        git(self.b, "add", ".")
        git(self.b, "commit", "-qm", "b")
        git(self.b, "push", "-q", "origin", "main")
        out = self.save("示例", "Quick note\n").stdout
        self.assertIn("switched from claude/session-x to main", out)
        self.assertIn("pushed: ", out)
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.a, "rev-parse", "HEAD"))
        self.assertEqual(git(self.origin, "branch", "--format=%(refname:short)").split(), ["main"])

    def test_nothing_written_when_sync_stops(self):
        git(self.a, "remote", "set-url", "origin", os.path.join(self.d, "gone.git"))
        p = self.save("示例", "Quick note\n", check=False)
        self.assertEqual(p.returncode, 4)
        self.assertIn("not saved: the checkout could not be brought up to date", p.stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.a, "Quick-Notes")))

    def test_refuses_class_a_and_empty(self):
        p = self.save("card", f"card {card_number()}\n", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("class-A candidate: line 1: card number", p.stdout)
        self.assertNotIn(card_number(), p.stdout)
        self.assertFalse(os.path.isdir(os.path.join(self.a, "Quick-Notes")))
        self.assertEqual(self.save("x", "  \n", check=False).returncode, 3)
        self.assertEqual(self.save("///", "x\n", check=False).returncode, 3)


class PackageCommitTest(Repo):
    def test_confirmed_preview_delivers_commits_and_pushes(self):
        out, work = os.path.join(self.d, "out"), os.path.join(self.d, "work")
        write(os.path.join(out, "02_Health_Report_A.md"), "new\n")
        write(os.path.join(out, "00_Spec.md"), "# Spec\nv2\n")
        write(os.path.join(out, "01_File-Index.md"), "index\n")
        write(os.path.join(out, "README.txt"), "readme\n")
        os.makedirs(work)
        write(os.path.join(self.a, "stray.md"), "not this round\n")  # left alone: never git add -A
        p = run("package.py", "preview", out, "--library", self.a, "--plan", os.path.join(work, "plan.json"),
                "--in-place", "--confirmed", "--commit", "入库：1 个文件")
        self.assertIn("Overwritten in place", p.stdout)
        self.assertIn("  write   | 02_Health_Report_A.md", p.stdout)
        self.assertIn("pushed: ", p.stdout)
        files = git(self.a, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(files), ["00_Spec.md", "01_File-Index.md", "02_Health_Report_A.md"])
        self.assertIn("?? stray.md", git(self.a, "status", "--porcelain"))
        self.assertEqual(self.last(self.a, "%an"), "Zhang San")

    def test_commit_needs_in_place(self):
        out, work = os.path.join(self.d, "out"), os.path.join(self.d, "work")
        write(os.path.join(out, "01_File-Index.md"), "index\n")
        write(os.path.join(out, "README.txt"), "readme\n")
        os.makedirs(work)
        p = run("package.py", "preview", out, "--library", self.a, "--plan", os.path.join(work, "plan.json"),
                "--confirmed", "--commit", "x", check=False)
        self.assertEqual(p.returncode, 2)
        self.assertIn("--commit is for a GitHub library", p.stdout)


if __name__ == "__main__":
    unittest.main()
