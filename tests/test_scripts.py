"""Unit tests for the kb-ingest scripts. Standard library only: python3 -m unittest discover tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "kb-ingest", "scripts")
sys.path.insert(0, SCRIPTS)
import kbconf  # noqa: E402


def run(script, *args, check=True):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise AssertionError(f"{script} {args} exited {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def p(self, *parts):
        return os.path.join(self.d, *parts)


class KbconfTest(Tmp):
    def test_defaults_and_overrides(self):
        write(self.p("lib", "_kb.json"), json.dumps({"schema": 1, "language": "zh", "timezone": "+08:00",
                                                     "names": {"status_card": "00_当前有效状态卡.md", "archive_dir": "归档"}}))
        cfg = kbconf.load_library(self.p("lib"))
        self.assertEqual(cfg["names"]["status_card"], "00_当前有效状态卡.md")
        self.assertEqual(cfg["names"]["status_card_key"], "当前有效状态卡")
        self.assertEqual(cfg["names"]["index"], "01_File-Index.md")
        self.assertEqual(cfg["names"]["archive_dir"], "归档")
        self.assertEqual(cfg["partitions"]["topic_start"], 2)

    def test_sources(self):
        self.assertEqual(kbconf.validate({"schema": 1, "sources": {"keep": True, "max_mb": 0}}), [])
        self.assertEqual(len(kbconf.validate({"schema": 1, "sources": {"keep": "yes", "max_mb": -1, "x": 1}})), 3)
        self.assertEqual(kbconf.resolve_names()["sources_dir"], "Sources")
        self.assertFalse(kbconf.DEFAULTS["sources"]["keep"])
        cfg = kbconf.merge(kbconf.DEFAULTS, {"sources": {"keep": True}})
        self.assertTrue(kbconf.keeps_sources(cfg))
        self.assertFalse(kbconf.keeps_sources(cfg, "github"))
        self.assertFalse(kbconf.keeps_sources(kbconf.DEFAULTS))

    def test_init_sources_by_preset(self):
        script = "init_library.py"
        base = ["--language", "en", "--timezone", "UTC", "--scope", "x"]
        out = run(script, "write", "--root", self.p("work"), "--preset", "work", *base).stdout
        self.assertIn("keep originals in the library: on", out)
        self.assertTrue(json.loads(read(self.p("work", "_kb.json")))["sources"]["keep"])
        run(script, "write", "--root", self.p("life"), "--preset", "life", *base)
        self.assertFalse(json.loads(read(self.p("life", "_kb.json")))["sources"]["keep"])
        self.assertFalse(os.path.exists(self.p("life", "Sources")))
        run(script, "write", "--root", self.p("life2"), "--preset", "life", *base, "--sources", "on")
        self.assertTrue(json.loads(read(self.p("life2", "_kb.json")))["sources"]["keep"])

    def test_validate_problems(self):
        problems = kbconf.validate({"schema": 2, "metadata": "xml", "bogus": 1,
                                    "partitions": {"max": 5, "topic_start": 2, "fallback": "07"},
                                    "names": {"nope": "x"}, "timezone": "Mars Base"})
        text = " ".join(problems)
        for word in ("schema", "metadata", "bogus", "fallback", "nope", "Mars Base"):
            self.assertIn(word, text)

    def test_timezone_check_is_version_independent(self):
        self.assertEqual(kbconf.check_timezone("Europe/London"), [])
        self.assertEqual(kbconf.check_timezone("+08:00"), [])
        self.assertTrue(kbconf.check_timezone("not a zone!"))

    def test_timezone_without_zone_data(self):
        # Python 3.8 has no zoneinfo: the system's own zone uses the current local offset, UTC names
        # are UTC, and any other name still asks for a fixed offset
        from unittest import mock
        with mock.patch.dict(sys.modules, {"zoneinfo": None}), \
                mock.patch.object(kbconf, "system_zone", return_value="Asia/Example"):
            self.assertEqual(kbconf.tzinfo("Asia/Example").utcoffset(None),
                             kbconf.datetime.now().astimezone().utcoffset())
            self.assertEqual(kbconf.tzinfo("Etc/UTC"), kbconf.timezone.utc)
            with self.assertRaises(kbconf.TimezoneUnavailable):
                kbconf.tzinfo("Europe/Elsewhere")
            self.assertEqual(kbconf.check_timezone("Europe/Elsewhere"), [])

    def test_limits(self):
        self.assertEqual(kbconf.default_limits("zh-CN"), (55, 80))
        self.assertEqual(kbconf.default_limits("en"), (90, 120))

    def test_registry(self):
        reg = {"schema": 1, "libraries": [
            {"id": "life", "label": "Life", "scope": "me", "backend": {"type": "local", "root": "~/kb"}},
            {"id": "life", "label": "Dup", "scope": "", "backend": {"type": "ftp"}}]}
        problems = " ".join(kbconf.check_registry(reg))
        self.assertIn("used twice", problems)
        self.assertIn("local is not supported", problems)
        self.assertIn("must be github", problems)
        reg["libraries"][1]["backend"] = {"type": "gdrive", "root": "x"}
        self.assertIn("gdrive is not supported: these skills serve GitHub libraries only (Google Drive libraries: "
                      "use walkwithedi/drive-wiki)", " ".join(kbconf.check_registry(reg)))
        self.assertIn("scope", problems)

    def test_registry_github(self):
        ok = {"schema": 1, "libraries": [
            {"id": "work", "label": "Work", "scope": "team", "backend": {"type": "github", "root": "octo/kb.work"}}]}
        self.assertEqual(kbconf.check_registry(ok), [])
        bad = {"schema": 1, "libraries": [
            {"id": "work", "label": "Work", "scope": "team", "backend": {"type": "github", "root": "kb"}}]}
        self.assertIn("<owner>/<repo>", " ".join(kbconf.check_registry(bad)))


class CleanTest(Tmp):
    def test_clean(self):
        src = self.p("in.md")
        write(src, "Converted by pandoc 3.1\n# \n\n# Real title\n\nBody one.\n\n\n\n"
                   "## This heading ends with a colon:\n| a |  | b |\n|---|---|---|\n| 1 |  | 2 |\n")
        out = run("clean.py", src, self.p("out.md"), "--max-heading-len", "90").stdout
        self.assertIn("header lines dropped 2", out)
        self.assertIn("empty columns dropped 1", out)
        self.assertIn("headings demoted 1", out)
        text = read(self.p("out.md"))
        self.assertTrue(text.startswith("# Real title"))
        self.assertIn("| a | b |", text)
        self.assertNotIn("\n\n\n", text)


class AssembleTest(Tmp):
    BODY = "# Release review\n\nThe launch moves to May. | a | b |\n\n| 1 | 2 |\n"

    def test_yaml_and_text_heads(self):
        write(self.p("body.md"), "\n" + self.BODY)
        for head in ('---\npartition: "05"\ntopic: "Release"\n---\n\n- Launch in May (source: Release review)\n',
                     "Partition: 05\nTopic: Release\n\n- Launch in May (source: Release review)"):
            with self.subTest(head=head[:12]):
                out = self.p("out", head[:3].strip("-\n") or "yaml", "05_Release_minutes_Review.md")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                write(self.p("head.md"), head)
                line = run("assemble.py", self.p("head.md"), self.p("body.md"), out).stdout.strip()
                self.assertEqual(line, f"assembled: 05_Release_minutes_Review.md | head {head.rstrip().count(chr(10)) + 1}"
                                       f" lines | body {len(self.BODY.strip())} characters")
                text = read(out)
                self.assertEqual(text, head.rstrip("\n") + "\n\n" + self.BODY)
                self.assertTrue(text.endswith(self.BODY))  # the body is copied as it is

    def test_refused(self):
        write(self.p("head.md"), "---\ntopic: \"x\"\n\n- conclusion\n")
        write(self.p("body.md"), "  \n")
        write(self.p("out.md"), "old")
        p = run("assemble.py", self.p("head.md"), self.p("body.md"), self.p("out.md"), check=False)
        self.assertEqual(p.returncode, 3)
        for reason in ("output file exists", "body is empty", "front matter opened with --- is not closed"):
            self.assertIn(reason, p.stdout)
        self.assertEqual(read(self.p("out.md")), "old")
        p = run("assemble.py", self.p("missing.md"), self.p("body.md"), self.p("new.md"), check=False)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(os.path.exists(self.p("new.md")))


class AssembleOriginalTest(Tmp):
    def setUp(self):
        super().setUp()
        write(self.p("body.md"), "Body text.\n")
        with open(self.p("scan.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 original bytes")
        os.makedirs(self.p("out"))

    def assemble(self, head, *extra, out="05_Release_minutes_Review.md"):
        write(self.p("head.md"), head)
        return run("assemble.py", self.p("head.md"), self.p("body.md"), self.p("out", out), *extra, check=False)

    def test_original_copied_and_linked(self):
        p = self.assemble('---\ntopic: "Release"\n---\n\n- Launch in May\n',
                          "--source", self.p("scan.pdf"), "--sources-dir", self.p("out", "Sources"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("| original kept: Sources/05_Release_minutes_Review.pdf", p.stdout)
        with open(self.p("out", "Sources", "05_Release_minutes_Review.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"%PDF-1.4 original bytes")
        text = read(self.p("out", "05_Release_minutes_Review.md"))
        self.assertTrue(text.startswith('---\ntopic: "Release"\noriginal: "[[Sources/05_Release_minutes_Review.pdf]]"\n---\n'))

    def test_text_head_gets_no_link(self):
        p = self.assemble("Topic: Release\n\n- Launch in May",
                          "--source", self.p("scan.pdf"), "--sources-dir", self.p("out", "Sources"))
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("original:", read(self.p("out", "05_Release_minutes_Review.md")))
        self.assertTrue(os.path.isfile(self.p("out", "Sources", "05_Release_minutes_Review.pdf")))

    def test_not_kept(self):
        p = self.assemble('---\ntopic: "x"\n---\n', "--source", self.p("missing.pdf"),
                          "--sources-dir", self.p("out", "Sources"))
        self.assertEqual(p.returncode, 0)
        self.assertIn("original not kept: file not found", p.stdout)
        self.assertNotIn("original:", read(self.p("out", "05_Release_minutes_Review.md")))
        with open(self.p("big.pdf"), "wb") as f:
            f.write(b"x" * (1024 * 1024 + 1))
        p = self.assemble('---\ntopic: "x"\n---\n', "--source", self.p("big.pdf"),
                          "--sources-dir", self.p("out", "Sources"), "--max-mb", "1", out="06_Other.md")
        self.assertIn("original not kept: larger than 1 MB", p.stdout)
        self.assertFalse(os.path.exists(self.p("out", "Sources")))

    def test_existing_copy_refused(self):
        write(self.p("out", "Sources", "05_Release_minutes_Review.pdf"), "old")
        p = self.assemble('---\ntopic: "x"\n---\n', "--source", self.p("scan.pdf"),
                          "--sources-dir", self.p("out", "Sources"))
        self.assertEqual(p.returncode, 3)
        self.assertIn("original copy exists", p.stdout)
        self.assertFalse(os.path.exists(self.p("out", "05_Release_minutes_Review.md")))


class IndexTest(Tmp):
    def setUp(self):
        super().setUp()
        self.idx = self.p("01_File-Index.md")
        write(self.idx, "# File index\n\nEntries: 1\nLast updated: 2026-01-01\n\n"
                        "| File name | Source file name |\n| --- | --- |\n| 02_Health_Report_A.md | a.pdf |\n")
        self.src = self.p("b (2).pdf")
        write(self.src, "content b")

    def test_add_check_write(self):
        run("index_tool.py", "add", self.idx, "--name", "03_Money_Plan_B.md", "--orig", "b (2).pdf", "--file", self.src)
        out = run("index_tool.py", "check", self.idx, "--orig", "b.pdf", "--name", "03_Money_Plan_B.md", "--file", self.src).stdout
        self.assertIn("Content hash: HIT", out)
        self.assertIn("Source name: HIT (hash matches)", out)
        self.assertIn("File name: HIT", out)
        run("index_tool.py", "write", self.idx, "--out", self.p("out.md"), "--date", "2026-10-10")
        text = read(self.p("out.md"))
        self.assertIn("Entries: 2", text)
        self.assertIn("Last updated: 2026-10-10", text)
        self.assertIn("| File name | Source file name | Source hash |", text)
        self.assertIn("| --- | --- | --- |", text)

    def test_add_twice_refused(self):
        p = run("index_tool.py", "add", self.idx, "--name", "02_Health_Report_A.md", "--orig", "x", check=False)
        self.assertEqual(p.returncode, 4)

    def test_chinese_index(self):
        idx = self.p("zh.md")
        write(idx, "条目数：1\n最后更新：2026-01-01\n文件名 ｜ 原始文件名\n02_体检_报告_甲.md ｜ 甲.pdf\n")
        run("index_tool.py", "add", idx, "--name", "02_体检_报告_乙.md", "--orig", "乙.pdf", "--file", self.src)
        run("index_tool.py", "write", idx, "--out", idx, "--date", "2026-10-10")
        text = read(idx)
        self.assertIn("条目数：2", text)
        self.assertIn("文件名 ｜ 原始文件名 ｜ 原文哈希", text)
        self.assertIn("02_体检_报告_乙.md ｜ 乙.pdf ｜ ", text)

    def test_refuses_library_index(self):
        lib = self.p("lib")
        write(os.path.join(lib, "_kb.json"), "{}")
        idx = os.path.join(lib, "01_File-Index.md")
        write(idx, read(self.idx))
        p = run("index_tool.py", "add", idx, "--name", "02_X.md", "--orig", "x", check=False)
        self.assertEqual(p.returncode, 5)
        p = run("index_tool.py", "write", self.idx, "--out", idx, "--date", "2026-10-10", check=False)
        self.assertEqual(p.returncode, 5)
        self.assertEqual(read(idx), read(self.idx))
        run("index_tool.py", "add", idx, "--name", "02_X.md", "--orig", "x", "--in-library")

    def test_empty_index(self):
        idx = self.p("empty.md")
        write(idx, "Entries: 0\nLast updated: 2026-01-01\n\n| File name | Source file name | Source hash |\n| --- | --- | --- |\n")
        self.assertEqual(run("index_tool.py", "write", idx, "--out", idx, "--date", "2026-10-10", check=False).returncode, 4)
        run("index_tool.py", "add", idx, "--name", "02_X_Y_Z.md", "--orig", "z.pdf")
        lines = read(idx).splitlines()
        self.assertEqual(lines[-1], "| 02_X_Y_Z.md | z.pdf |")


class CardCheckTest(Tmp):
    def test_pass_and_fail(self):
        old = self.p("old.md")
        new = self.p("new.md")
        changes = self.p("changes.txt")
        write(old, "# Status card\nLast updated: 2026-01-01\n1. Limit is 10 GB (basis: [[a]])\n2. Owner is Team A (basis: [[b]])\n")
        write(new, "# Status card\nLast updated: 2026-10-10\n1. Limit is 20 GB (basis: [[c]])\n2. Owner is Team A (basis: [[b]])\n")
        write(changes, "")
        p = run("card_check.py", old, new, "--changes", changes, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("1 unexplained losses", p.stdout)
        write(changes, "Item 1: Limit is 10 GB (basis: [[a]]) -> Limit is 20 GB (basis: [[c]])\n")
        p = run("card_check.py", old, new, "--changes", changes)
        self.assertIn("Result: passed", p.stdout)

    def test_locked_fields(self):
        old, new = self.p("o.md"), self.p("n.md")
        write(old, '---\ntype: "entity"\naliases: ["A", "B"]\n---\n# Atlas\ntext\n')
        write(new, '---\ntype: "note"\naliases: ["A"]\n---\n# Atlas2\ntext\n')
        out = run("card_check.py", old, new, check=False).stdout
        self.assertIn("locked field changed: type", out)
        self.assertIn("aliases lost entries", out)
        self.assertIn("level-1 heading changed", out)


class EvidenceCheckTest(Tmp):
    def setUp(self):
        super().setUp()
        write(self.p("src", "02_Checkups_report_2025-annual.md"),
              "# Report\nTotal cholesterol 5.6 mmol/L (reference below 5.2). Next visit: 2026年11月1日.\n"
              "The doctor wrote “复查前空腹十二小时”. Fee 1,200.\n")
        write(self.p("src", "Entities", "Atlas.md"), "# Atlas\nBudget 15.6 per year, started 2026-03.\n")

    def check(self, card, *args):
        write(self.p("card.md"), card)
        return run("evidence_check.py", self.p("card.md"), "--sources", self.p("src"), *args).stdout

    def test_found_values(self):
        out = self.check(
            "# Status card\nLast updated: 2026-10-10\n\n## Items\n\n"
            "1. Cholesterol 5.6 mmol/L, above 5.2; follow-up on 2026-11-01 (basis: [[02_Checkups_report_2025-annual]])\n"
            "2. Fasting rule: 「复查前空腹十二小时」; fee 1200 (basis: [[02_Checkups_report_2025-annual|report]])\n"
            "3. Atlas started 2026年3月 (basis: [Atlas](Entities/Atlas.md))\n")
        self.assertIn("3 items, 6 values checked, 0 not found, 0 without basis link, 0 with basis file missing", out)

    def test_suspects(self):
        out = self.check(
            "1. Cholesterol 5.8 mmol/L; follow-up on 2026-12-01 (basis: [[02_Checkups_report_2025-annual]])\n"
            "2. Atlas budget 5.6 per year (basis: [[Atlas]])\n"
            "3. Owner changed in 12 months\n"
            "4. Limit 10% (basis: [[Missing-file]])\n")
        self.assertIn("Item 1 (line 1): number not found in 02_Checkups_report_2025-annual: 5.8", out)
        self.assertIn("Item 1 (line 1): date not found in 02_Checkups_report_2025-annual: 2026-12-01", out)
        self.assertIn("Item 2 (line 2): number not found in Atlas: 5.6", out)
        self.assertIn("Item 3 (line 3): no basis link", out)
        self.assertIn("Item 4 (line 4): basis file not in sources folder: Missing-file", out)

    def test_item_filter_and_bad_folder(self):
        out = self.check("1. Value 5.8 (basis: [[Atlas]])\n2. Value 15.6 (basis: [[Atlas]])\n", "--item", "2")
        self.assertIn("1 items, 1 values checked, 0 not found", out)
        p = run("evidence_check.py", self.p("card.md"), "--sources", self.p("nope"), check=False)
        self.assertEqual(p.returncode, 2)



class PackageTest(Tmp):
    def setUp(self):
        super().setUp()
        self.lib = self.p("lib")
        write(os.path.join(self.lib, "_kb.json"), json.dumps({"schema": 1, "label": "Life", "timezone": "UTC"}))
        write(os.path.join(self.lib, "02_Health_Report_A.md"), "old version\n")
        self.out = self.p("out")
        write(os.path.join(self.out, "02_Health_Report_A.md"), "new version\n")
        write(os.path.join(self.out, "02_Health_Report_B.md"), "brand new\n")
        write(os.path.join(self.out, "01_File-Index.md"), "index\n")
        write(os.path.join(self.out, "README.txt"), "readme\n")
        write(os.path.join(self.out, "Entities", "Self.md"), "entity\n")

    def test_preview_and_deliver(self):
        plan = self.p("plan.json")
        out = run("package.py", "preview", self.out, "--library", self.lib, "--plan", plan).stdout
        self.assertIn("New versions (old copy goes to Archive/): 1", out)
        self.assertEqual(read(os.path.join(self.lib, "02_Health_Report_A.md")), "old version\n")
        run("package.py", "deliver", "--plan", plan)
        self.assertEqual(read(os.path.join(self.lib, "02_Health_Report_A.md")), "new version\n")
        arch = os.listdir(os.path.join(self.lib, "Archive"))
        self.assertTrue(any(n.startswith("02_Health_Report_A_old") for n in arch))
        self.assertTrue(any(n.startswith("_run-log_") for n in arch))
        self.assertTrue(any(n.endswith("_README.txt") for n in arch))
        self.assertTrue(os.path.isfile(os.path.join(self.lib, "Entities", "Self.md")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "README.txt")))

    def test_preview_and_deliver_in_place(self):
        plan = self.p("work", "plan.json")
        os.makedirs(os.path.dirname(plan))
        out = run("package.py", "preview", self.out, "--library", self.lib, "--plan", plan, "--in-place").stdout
        self.assertIn("Overwritten in place (git history keeps the old version): 1", out)
        self.assertIn("  = 02_Health_Report_A.md (+1 -1 lines)", out)
        self.assertNotIn("Archive/", out)
        run("package.py", "deliver", "--plan", plan)
        self.assertEqual(read(os.path.join(self.lib, "02_Health_Report_A.md")), "new version\n")
        self.assertEqual(read(os.path.join(self.lib, "02_Health_Report_B.md")), "brand new\n")
        self.assertFalse(os.path.exists(os.path.join(self.lib, "Archive")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "README.txt")))
        work = os.listdir(os.path.dirname(plan))
        self.assertTrue(any(n.startswith("_run-log_") for n in work))
        self.assertTrue(any(n.endswith("_README.txt") for n in work))

    def test_in_place_refuses_repository_files_and_originals(self):
        write(os.path.join(self.out, "CLAUDE.md"), "rules\n")
        os.makedirs(os.path.join(self.out, "Sources"))
        with open(os.path.join(self.out, "Sources", "02_Health_Report_B.pdf"), "wb") as f:
            f.write(b"%PDF")
        p = run("package.py", "preview", self.out, "--library", self.lib, "--plan", self.p("plan.json"),
                "--in-place", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("repository file must not be delivered: CLAUDE.md", p.stdout)
        self.assertIn("delivered only into a local library", p.stdout)

    def originals(self):
        """The library keeps originals: A had a .docx original; this run brings A as a .pdf, B new with a
        .xlsx, and a new version of C (pasted text, no original)."""
        src = os.path.join(self.lib, "Sources")
        for name, data in (("02_Health_Report_A.docx", b"old a"), ("02_Health_Report_C.pdf", b"old c"),
                           ("02_Health_Report_D.pdf", b"untouched")):
            os.makedirs(src, exist_ok=True)
            with open(os.path.join(src, name), "wb") as f:
                f.write(data)
        write(os.path.join(self.lib, "02_Health_Report_C.md"), "old c\n")
        write(os.path.join(self.out, "02_Health_Report_C.md"), "new c\n")
        for name, data in (("02_Health_Report_A.pdf", b"%PDF new a"), ("02_Health_Report_B.xlsx", b"PK\x03\x04 b")):
            os.makedirs(os.path.join(self.out, "Sources"), exist_ok=True)
            with open(os.path.join(self.out, "Sources", name), "wb") as f:
                f.write(data)

    def test_originals_delivered_and_old_ones_archived(self):
        self.originals()
        plan = self.p("plan.json")
        out = run("package.py", "preview", self.out, "--library", self.lib, "--plan", plan).stdout
        self.assertIn("+ Sources/02_Health_Report_A.pdf", out)
        self.assertIn("+ Sources/02_Health_Report_B.xlsx", out)
        self.assertIn("~ Sources/02_Health_Report_A.docx  old original, no new copy -> Archive/", out)
        self.assertIn("~ Sources/02_Health_Report_C.pdf  old original, no new copy -> Archive/", out)
        self.assertNotIn("Report_D", out)
        run("package.py", "deliver", "--plan", plan)
        src = os.path.join(self.lib, "Sources")
        self.assertEqual(sorted(os.listdir(src)), ["02_Health_Report_A.pdf", "02_Health_Report_B.xlsx",
                                                   "02_Health_Report_D.pdf"])
        with open(os.path.join(src, "02_Health_Report_A.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"%PDF new a")
        arch = os.listdir(os.path.join(self.lib, "Archive"))
        for stem, ext in (("02_Health_Report_A", ".docx"), ("02_Health_Report_C", ".pdf"), ("02_Health_Report_C", ".md")):
            self.assertTrue(any(n.startswith(stem + "_old") and n.endswith(ext) for n in arch), (stem, ext, arch))

    def test_original_with_the_same_name_is_archived_once(self):
        self.originals()
        with open(os.path.join(self.out, "Sources", "02_Health_Report_C.pdf"), "wb") as f:
            f.write(b"new c")
        plan = self.p("plan.json")
        run("package.py", "preview", self.out, "--library", self.lib, "--plan", plan)
        rels = [i["rel"] for i in json.loads(read(plan))["items"]]
        self.assertEqual(rels.count("Sources/02_Health_Report_C.pdf"), 1)
        run("package.py", "deliver", "--plan", plan)
        with open(os.path.join(self.lib, "Sources", "02_Health_Report_C.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"new c")

    def test_default_delivery(self):
        self.assertEqual(kbconf.default_delivery({}, "github"), "direct")
        self.assertEqual(kbconf.default_delivery({"inbox": {"folder": "x"}}, "github"), "direct")
        self.assertIn("delivery must be direct", " ".join(kbconf.validate({"schema": 1, "delivery": "zip"})))

    def test_deliver_detects_change(self):
        plan = self.p("plan.json")
        run("package.py", "preview", self.out, "--library", self.lib, "--plan", plan)
        time.sleep(0.01)
        write(os.path.join(self.lib, "02_Health_Report_A.md"), "edited meanwhile, longer\n")
        p = run("package.py", "deliver", "--plan", plan, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("target changed after preview", p.stdout)
        self.assertEqual(read(os.path.join(self.lib, "02_Health_Report_A.md")), "edited meanwhile, longer\n")


class BatchPlanTest(Tmp):
    def setUp(self):
        super().setUp()
        write(self.p("lib", "_kb.json"), json.dumps({"schema": 1, "intake": {"batch_files": 2}}))
        write(self.p("known.docx"), "already filed")
        h = run("index_tool.py", "hash", self.p("known.docx")).stdout.strip()
        write(self.p("lib", "01_File-Index.md"), "| File name | Source file name | Source hash |\n| --- | --- | --- |\n"
                                                 f"| 03_Projects_Report_Old.md | known.docx | {h} |\n")
        write(self.p("lib", "03_Projects_Report_Old.md"), "never material")
        for i in range(3):
            write(self.p("mat", "Alpha", f"a{i}.docx"), f"alpha {i}")
        write(self.p("mat", "Beta", "deep", "b.pdf"), "beta")
        write(self.p("mat", "Beta", "again.docx"), "already filed")
        write(self.p("mat", "Beta", "copy.pdf"), "alpha 0")
        write(self.p("mat", "Beta", "pack.zip"), "zip")
        write(self.p("mat", "Beta", "~$lock.docx"), "lock")
        write(self.p("mat", "loose.txt"), "loose")
        self.plan = self.p("lib", "_intake-batches.json")

    def bp(self, *args, check=True):
        return run("batch_plan.py", *args, "--plan", self.plan, check=check)

    def make_plan(self, *extra):
        return run("batch_plan.py", "plan", self.p("mat"), self.p("lib"), "--plan", self.plan,
                   "--library-root", self.p("lib"), "--index", self.p("lib", "01_File-Index.md"), *extra)

    def test_plan_groups_limits_and_exclusions(self):
        out = self.make_plan().stdout
        self.assertIn("left out, duplicates: 2", out)
        self.assertIn("already in the library as 03_Projects_Report_Old.md", out)
        self.assertIn("same content as mat/Alpha/a0.docx", out)
        self.assertIn("archive: unpack it first", out)
        self.assertNotIn("lock", out)
        self.assertIn("batches: 4", out)
        plan = json.loads(read(self.plan))
        got = [(b["group"], b["part"], [f["rel"] for f in b["files"]]) for b in plan["batches"]]
        self.assertEqual(got, [("mat/Alpha", "1/2", ["mat/Alpha/a0.docx", "mat/Alpha/a1.docx"]),
                               ("mat/Alpha", "2/2", ["mat/Alpha/a2.docx"]),
                               ("mat/Beta", "", ["mat/Beta/deep/b.pdf"]),
                               ("mat/(loose files)", "", ["mat/loose.txt"])])
        self.assertTrue(all(f["kind"] in ("convert", "text") for b in plan["batches"] for f in b["files"]))

    def test_first_and_size_limit(self):
        out = self.make_plan("--first", "Beta", "--batch-files", "5").stdout
        self.assertIn("batch 1: mat/Beta |", out)
        self.assertIn("batch 2: mat/Alpha |", out)

    def test_single_batch_writes_nothing(self):
        out = run("batch_plan.py", "plan", self.p("mat", "Alpha"), "--plan", self.plan, "--batch-files", "10").stdout
        self.assertIn("one batch, no batching needed", out)
        self.assertFalse(os.path.exists(self.plan))

    def test_progress_and_resume(self):
        self.make_plan()
        nxt = self.bp("next").stdout
        self.assertIn("batch: 1/4 | mat/Alpha part 1/2 | 2 files", nxt)
        self.assertIn("file: " + self.p("mat", "Alpha", "a0.docx"), nxt)
        self.bp("done", "--batch", "1", "--written", "2")
        self.bp("skip", "--batch", "2")
        self.bp("add", "--batch", "3", "--kind", "trigger", "--text", "status card item 4: new deadline",
                "--file", "b.pdf")
        self.bp("add", "--batch", "3", "--kind", "review", "--text", "renamed to distinguish")
        p = run("batch_plan.py", "plan", self.p("mat"), "--plan", self.plan, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("a plan with pending batches exists", p.stdout)
        self.assertIn("--append", p.stdout)
        status = self.bp("status").stdout
        self.assertIn("batches: 4 | done 1 | skipped 1 | pending 2", status)
        self.assertIn("next: batch 3 mat/Beta", status)
        self.assertIn("batch 3 [b.pdf]: status card item 4: new deadline", status)
        self.bp("done", "--batch", "3")
        self.bp("done", "--batch", "4")
        self.assertEqual(self.bp("next", check=False).returncode, 1)
        fin = self.bp("finish").stdout
        self.assertIn("renamed to distinguish", fin)
        self.assertIn("final step: done", fin)
        self.assertIn("result: archive the plan", fin)
        self.assertNotIn("renamed to distinguish", self.bp("status").stdout)
        self.assertEqual(run("batch_plan.py", "plan", self.p("mat"), "--plan", self.plan).returncode, 0)

    def test_append_new_sources(self):
        self.make_plan()
        write(self.p("other", "Gamma", "g1.docx"), "gamma 1")
        write(self.p("other", "Gamma", "g2.docx"), "gamma 2")
        write(self.p("other", "Gamma", "dup.docx"), "alpha 1")  # same content as a file in the run
        out = run("batch_plan.py", "plan", self.p("other"), "--plan", self.plan, "--append",
                  "--library-root", self.p("lib")).stdout
        self.assertIn("same content as mat/Alpha/a1.docx", out)
        self.assertIn("1 batches added", out)
        plan = json.loads(read(self.plan))
        self.assertEqual([b["n"] for b in plan["batches"]], [1, 2, 3, 4, 5])
        self.assertEqual(plan["batches"][-1]["group"], "other/Gamma")
        self.assertIn(self.p("other"), plan["sources"])
        write(self.p("third", "t.txt"), "third")
        write(self.p("third", "u.txt"), "third u")
        write(self.p("third", "v.txt"), "third v")
        run("batch_plan.py", "plan", self.p("third"), "--plan", self.plan, "--append", "--front",
            "--library-root", self.p("lib"))
        plan = json.loads(read(self.plan))
        self.assertEqual(plan["batches"][0]["group"], "third/(loose files)")
        self.assertIn("batch: 6/7 | third/(loose files) part 1/2", self.bp("next").stdout)

    def test_interrupted_batch_resumes(self):
        self.make_plan()
        index = self.p("lib", "01_File-Index.md")
        self.assertNotIn("resumed", self.bp("next").stdout)
        status = self.bp("status").stdout
        self.assertIn("interrupted, started", status)
        # a0 was filed before the interruption
        h = run("index_tool.py", "hash", self.p("mat", "Alpha", "a0.docx")).stdout.strip()
        with open(index, "a", encoding="utf-8") as f:
            f.write(f"| 03_Projects_Alpha.md | a0.docx | {h} |\n")
        nxt = run("batch_plan.py", "next", "--plan", self.plan, "--index", index).stdout
        self.assertIn("resumed (interrupted)", nxt)
        self.assertIn("filed: " + self.p("mat", "Alpha", "a0.docx") + " as 03_Projects_Alpha.md", nxt)
        self.assertIn("file: " + self.p("mat", "Alpha", "a1.docx"), nxt)

    def test_missing_batch_and_skip_rest(self):
        self.make_plan()
        shutil.rmtree(self.p("mat", "Alpha"))
        p = self.bp("next", check=False)
        self.assertEqual(p.returncode, 4)
        self.assertIn("missing folder: " + self.p("mat", "Alpha"), p.stdout)
        self.assertNotIn("started", read(self.plan))
        self.bp("skip", "--rest")
        self.assertIn("batches: 4 | done 0 | skipped 4 | pending 0", self.bp("status").stdout)
        self.assertEqual(self.bp("skip", check=False).returncode, 2)

    def test_bad_input(self):
        self.make_plan()
        self.assertEqual(self.bp("done", "--batch", "9", check=False).returncode, 2)
        self.assertEqual(run("batch_plan.py", "plan", self.p("nope"), "--plan", self.p("x.json"), check=False).returncode, 2)
        problems = kbconf.validate({"schema": 1, "intake": {"batch_files": 0, "pages": 3}})
        self.assertIn("intake.batch_files must be a whole number of 1 or more", problems)
        self.assertIn("unknown intake key 'pages'", problems)


class InitLibraryTest(Tmp):
    def test_write_matches_preset(self):
        root = self.p("kb", "life")
        out = run("init_library.py", "write", "--root", root, "--preset", "life", "--language", "zh",
                  "--timezone", "+08:00", "--scope", "我和家人", "--date", "2026-10-10").stdout
        self.assertIn("result: written 8 files and 0 folders", out)  # git keeps no empty folders
        cfg = kbconf.load_library(root)
        self.assertEqual((cfg["label"], cfg["language"], cfg["timezone"]), ("生活", "zh", "+08:00"))
        self.assertTrue(cfg["sensitivity"]["enabled"])
        self.assertEqual(kbconf.validate(json.loads(read(os.path.join(root, "_kb.json")))), [])
        names = cfg["names"]
        spec = read(os.path.join(root, names["spec"]))
        self.assertIn("Last updated: 2026-10-10", spec)
        self.assertIn("| 55", spec)
        self.assertNotIn("{{", spec)
        for k in kbconf.SUMMARY_KEYS:
            self.assertNotIn("{{", read(os.path.join(root, names[k])))
        self.assertIn("Entries: 0", read(os.path.join(root, names["index"])))

    def test_work_preset_follows_language(self):
        for lang, heading, field, index in (("zh", "表 A（Table A）：分区与主题", "entities:", "条目数：0"),
                                            ("en", "Table A: partitions and topics", "entities:", "Entries: 0")):
            root = self.p("kb", "work-" + lang)
            run("init_library.py", "write", "--root", root, "--preset", "work", "--language", lang,
                "--timezone", "UTC", "--scope", "x", "--date", "2026-10-10")
            names = kbconf.load_library(root)["names"]
            spec = read(os.path.join(root, names["spec"]))
            self.assertIn(heading, spec)
            self.assertIn(field, spec)
            self.assertNotIn("systems", spec)
            self.assertNotIn("{{", spec)
            self.assertIn(index, read(os.path.join(root, names["index"])))
            for k in kbconf.SUMMARY_KEYS:
                self.assertNotIn("{{", read(os.path.join(root, names[k])))
            self.assertNotIn("{{", read(os.path.join(root, kbconf.PARAMS_FILE)))

    def test_refuses_existing_library(self):
        root = self.p("lib")
        write(os.path.join(root, "notes.md"), "mine\n")
        p = run("init_library.py", "write", "--root", root, "--preset", "work", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertEqual(os.listdir(root), ["notes.md"])

    def test_register_and_instructions(self):
        reg = self.p("cfg", "kb-libraries.json")
        run("init_library.py", "register", "--registry", reg, "--id", "life", "--label", "Life",
            "--scope", "me and my family", "--type", "github", "--root", "me/life")
        run("init_library.py", "register", "--registry", reg, "--id", "work", "--label", "Work",
            "--scope", "team projects", "--type", "github", "--root", "me/work")
        p = run("init_library.py", "register", "--registry", reg, "--id", "work", "--label", "W",
                "--scope", "x", "--type", "github", "--root", "me/zzz", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertEqual([lib["id"] for lib in kbconf.load_registry(reg)["libraries"]], ["life", "work"])
        md = self.p("CLAUDE.md")
        write(md, "# My rules\n\nBe brief.\n")
        out = run("init_library.py", "instructions", "--registry", reg, "--file", md).stdout
        self.assertIn("would be added", out)
        self.assertEqual(read(md), "# My rules\n\nBe brief.\n")
        run("init_library.py", "instructions", "--registry", reg, "--file", md, "--apply")
        text = read(md)
        self.assertIn("Be brief.", text)
        self.assertIn("I keep knowledge bases: Life (me and my family); Work (team projects).", text)
        self.assertIn("unfinished batch intake, ask whether to continue it.", text)
        out = run("init_library.py", "instructions", "--registry", reg, "--file", md, "--apply").stdout
        self.assertIn("unchanged", out)
        block = run("init_library.py", "instructions", "--registry", reg, "--project-block").stdout
        self.assertIn("Knowledge base registry (kb-libraries.json):", block)
        self.assertIn('"root": "me/work"', block)

    def test_every_preset_has_defaults(self):
        sys.path.insert(0, SCRIPTS)
        import init_library as il
        presets = sorted(os.listdir(il.PRESETS_DIR))
        self.assertEqual(presets, sorted(il.PRESETS))
        for p in presets:
            self.assertEqual(sorted(il.PRESET_DEFAULTS[p]), sorted(il.LANGUAGES))

    def test_upsert_line(self):
        sys.path.insert(0, SCRIPTS)
        import init_library as il
        text, what = il.upsert_line("a\n我有知识库：旧（x）。\nb\n", "I keep knowledge bases: New (y).")
        self.assertEqual(what, "updated")
        self.assertEqual(text, "a\nI keep knowledge bases: New (y).\nb\n")
        self.assertEqual(il.upsert_line("", "L")[0], "L\n")

    def test_github_checkout(self):
        root = self.p("repo")
        write(os.path.join(root, "README.md"), "# repo\n")
        write(os.path.join(root, ".gitignore"), "x\n")
        p = run("init_library.py", "write", "--root", root, "--preset", "work", "--language", "en",
                "--timezone", "UTC", "--scope", "x", "--backend", "github", check=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("result: written 8 files and 0 folders", p.stdout)
        self.assertIn("| backend github |", p.stdout)
        self.assertEqual([n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))], [])
        self.assertEqual(read(os.path.join(root, "README.md")), "# repo\n")
        other = self.p("repo2")
        write(os.path.join(other, "README.md"), "# repo\n")
        write(os.path.join(other, "notes.md"), "mine\n")
        self.assertEqual(run("init_library.py", "plan", "--root", other, "--preset", "work",
                             "--backend", "github", check=False).returncode, 3)

    def test_github_register_and_block(self):
        reg = self.p("work", "kb-libraries.json")
        run("init_library.py", "register", "--registry", reg, "--id", "work", "--label", "Work",
            "--scope", "team projects", "--type", "github", "--root", "alex/work-notes")
        p = run("init_library.py", "register", "--registry", self.p("bad.json"), "--id", "w", "--label", "W",
                "--scope", "x", "--type", "github", "--root", "not a repo", check=False)
        self.assertEqual(p.returncode, 2)
        md = self.p("CLAUDE.md")
        write(md, "# Rules\n\nBe brief.\n")
        out = run("init_library.py", "instructions", "--registry", reg, "--file", md, "--block").stdout
        self.assertIn("would be added", out)
        self.assertEqual(read(md), "# Rules\n\nBe brief.\n")
        run("init_library.py", "instructions", "--registry", reg, "--file", md, "--block", "--apply")
        text = read(md)
        self.assertTrue(text.startswith("# Rules\n\nBe brief.\n\nI keep knowledge bases: Work (team projects)."))
        self.assertIn("Knowledge base registry (kb-libraries.json):\n\n```json\n{", text)
        sys.path.insert(0, SCRIPTS)
        import init_library as il
        self.assertEqual(il.block_registry(text)["libraries"][0]["backend"],
                         {"type": "github", "root": "alex/work-notes"})
        out = run("init_library.py", "instructions", "--registry", reg, "--file", md, "--block", "--apply").stdout
        self.assertIn("unchanged", out)
        # a changed scope replaces the block in place; text after it stays
        write(md, read(md) + "\nAfter.\n")
        data = json.loads(read(reg))
        data["libraries"][0]["scope"] = "team work"
        write(reg, json.dumps(data))
        out = run("init_library.py", "instructions", "--registry", reg, "--file", md, "--block", "--apply").stdout
        self.assertIn("updated", out)
        text = read(md)
        self.assertEqual(text.count("I keep knowledge bases"), 1)
        self.assertEqual(text.count("```json"), 1)
        self.assertIn("Work (team work)", text)
        self.assertTrue(text.endswith("```\n\nAfter.\n"))
        # another library in the same file is refused
        reg2 = self.p("other", "kb-libraries.json")
        run("init_library.py", "register", "--registry", reg2, "--id", "life", "--label", "Life",
            "--scope", "me", "--type", "github", "--root", "alex/life-notes")
        p = run("init_library.py", "instructions", "--registry", reg2, "--file", md, "--block", "--apply", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("Work (team work)", read(md))

    def test_upsert_block_moves_stray_line(self):
        sys.path.insert(0, SCRIPTS)
        import init_library as il
        reg = {"schema": 1, "preferences": {"language": "zh"}, "libraries": [
            {"id": "work", "label": "工作库", "scope": "工作", "backend": {"type": "github", "root": "a/b"}}]}
        old = ("# 约定\n\n我有知识库：旧（x）。\n\n说明。\n\n知识库注册表（kb-libraries.json）：\n\n```json\n"
               + json.dumps(dict(reg, libraries=[dict(reg["libraries"][0], scope="旧")])) + "\n```\n\n## 规则\n")
        text, what = il.upsert_block(old, reg)
        self.assertEqual(what, "updated")
        self.assertEqual(text.count("我有知识库"), 1)
        self.assertIn("说明。\n\n我有知识库：工作库（工作）。", text)
        self.assertTrue(text.endswith("```\n\n## 规则\n"))
        self.assertEqual(il.upsert_block(text, reg), (text, "unchanged"))


SPEC_EN = """# Spec

2. Table B: term fixes

Original | Fixed | Note
Atlass | Atlas | typo

5. Table E: entities

| Name | Type | Aliases | Core | Note |
| --- | --- | --- | --- | --- |
| Project Atlas | project | Atlas; (PA) | yes | |
| Payments Gateway | system | | no | |

Only names in Table E may be written as links.

6. Table F: value filters

Empty-value forms | Noise values | Maintenance
none; n/a; - | placeholders, generic words such as "system" or "platform" | add new noise

7. Naming
"""


class MetaTest(Tmp):
    def test_name(self):
        out = run("meta.py", "name", "--partition", "05", "--topic", "Primary home", "--type", "report",
                  "--title", "Roof repair: quote/2026", "--language", "en").stdout
        self.assertEqual(out.split(" | ")[0], "05_Primary-home_report_Roof-repair-quote-2026.md")
        p = run("meta.py", "name", "--partition", "05", "--topic", "x", "--type", "y", "--title", "a" * 100,
                "--max-len", "60", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("shorten the short title by 50", p.stdout)
        p = run("meta.py", "name", "--partition", "05", "--topic", "x", "--type", "y", "--title", "///", check=False)
        self.assertEqual(p.returncode, 3)

    def test_entities(self):
        write(self.p("spec.md"), SPEC_EN)
        out = run("meta.py", "entities", self.p("spec.md"),
                  "--field", "entities=Atlas, PA, payments gateway, n/a, system, the vendor (east, west)",
                  "--keywords", "Atlas, settlement").stdout
        self.assertIn("Table E: 2 entities; Table F: 3 empty-value forms, 2 quoted noise values", out)
        self.assertIn("  Atlas -> [[Project Atlas]]", out)
        self.assertIn("  PA -> [[Project Atlas]]", out)  # brackets around an alias are not part of it
        self.assertIn("payments gateway -> no match: decide (entity to register, plain text, or alias); "
                      "possible alias of: Payments Gateway", out)
        self.assertIn("n/a -> dropped (empty-value form in Table F)", out)
        self.assertIn("system -> dropped (noise value in Table F)", out)
        self.assertIn("the vendor (east, west) -> no match", out)  # not split inside brackets
        self.assertIn('  entities: ["[[Project Atlas]]", "payments gateway", "the vendor (east, west)"]', out)
        self.assertIn('  entities_note: "Atlas, PA, payments gateway, n/a, system, the vendor (east, west)"', out)
        self.assertIn('  keywords: ["[[Project Atlas]]", "settlement"]', out)

    def test_terms(self):
        write(self.p("spec.md"), SPEC_EN)
        write(self.p("body.md"), "# Notes\n\nAtlass starts in May.\nNothing here.\n")
        out = run("meta.py", "terms", self.p("spec.md"), self.p("body.md")).stdout
        self.assertIn("Atlass -> Atlas: 1 lines", out)
        self.assertIn("  line 3: Atlass starts in May.", out)
        write(self.p("body.md"), "clean\n")
        self.assertIn("Term fixes: none", run("meta.py", "terms", self.p("spec.md"), self.p("body.md")).stdout)

    def test_yaml(self):
        write(self.p("f.json"), json.dumps({"event_date": "2025-10-02", "file_date": "2025-10-06 09:14",
                                            "partition": "02", "topic": 'Say "hi" \\ there',
                                            "people": ["[[Self]]"], "size": None, "source_characters": 1840}))
        self.assertEqual(run("meta.py", "yaml", self.p("f.json")).stdout,
                         '---\nevent_date: 2025-10-02\nfile_date: 2025-10-06T09:14\npartition: "02"\n'
                         'topic: "Say \\"hi\\" \\\\ there"\npeople: ["[[Self]]"]\nsource_characters: 1840\n---\n')
        write(self.p("f.json"), "[1]")
        self.assertEqual(run("meta.py", "yaml", self.p("f.json"), check=False).returncode, 3)

    def test_date(self):
        doc = self.p("a.docx")
        with zipfile.ZipFile(doc, "w") as z:
            z.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
                       'package/2006/metadata/core-properties" xmlns:dcterms="http://purl.org/dc/terms/">'
                       '<dcterms:modified>2025-03-04T05:06:00Z</dcterms:modified></cp:coreProperties>')
        write(self.p("b.txt"), "x")
        out = run("meta.py", "date", doc, self.p("b.txt"), "--timezone", "+08:00").stdout.splitlines()
        self.assertEqual(out[0], "a.docx | 2025-03-04 13:06 | document metadata | +08:00")
        self.assertIn("file system time, unreliable", out[1])


QUERY = os.path.join(ROOT, "skills", "kb-query", "scripts", "kbfind.py")


def kbfind(*args):
    p = subprocess.run([sys.executable, QUERY, *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise AssertionError(f"kbfind {args} exited {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p.stdout


class KbFindTest(Tmp):
    def setUp(self):
        super().setUp()
        write(self.p("lib", "_kb.json"), json.dumps({"schema": 1, "names": {"old_suffix": "_alt"}}))
        card = ["# Status card", "", "## Payments", ""] + [f"{i}. Item {i} about routine things" for i in range(1, 40)]
        card += ["40. Settlement window moves to 18:00 (basis: [[05_Ops_minutes_Window]])", "    continued line", "",
                 "## Projects", "", "Atlas launches in May; the settlement report follows.", "",
                 "| Item | Owner |", "| --- | --- |", "| Settlement report | Finance |"]
        write(self.p("lib", "00_Status-Card.md"), "\n".join(card) + "\n")
        write(self.p("lib", "05_Ops_minutes_Window.md"), "---\ntopic: \"Settlement\"\n---\n\nBody.\n")
        write(self.p("lib", "05_Ops_minutes_Window_alt20260101120000.md"), "settlement old\n")
        write(self.p("lib", "_intake-batches.json"), "settlement")
        write(self.p("lib", "_note.md"), "settlement")
        write(self.p("lib", "snapshot_card.md"), "settlement")
        write(self.p("lib", "Archive", "x.md"), "settlement")
        write(self.p("lib", "Entities", "Atlas.md"), "# Atlas\n\nSettlement owner.\n")
        write(self.p("lib", "README.md"), "settlement\n")
        write(self.p("lib", "CLAUDE.md"), "settlement\n")

    def test_find_blocks(self):
        out = kbfind("find", self.p("lib"), "SETTLEMENT")
        self.assertIn("files searched: 2 | files with hits: 2 | blocks: 4", out)
        self.assertIn("-- lines 44-45 | Status card > Payments\n40. Settlement window moves to 18:00", out)
        self.assertIn("continued line", out)
        self.assertIn("| Status card > Projects\nAtlas launches in May", out)
        self.assertIn("| Item | Owner |\n| Settlement report | Finance |", out)  # the header row comes along
        self.assertIn("-- lines 1-3 | (no heading) | front matter", out)
        for skipped in ("old", "Archive", "snapshot", "_note", "Entities"):
            self.assertNotIn(skipped, out.split("\n", 1)[1])
        self.assertNotIn("Item 5 about", out)

    def test_find_options_and_caps(self):
        out = kbfind("find", self.p("lib"), "settlement", "atlas", "--all")
        self.assertIn("blocks: 1", out)
        out = kbfind("find", self.p("lib"), "item", "--file", "Status-Card", "--max-per-file", "3")
        self.assertIn("files searched: 1", out)
        self.assertIn("more blocks in this file", out)
        out = kbfind("find", self.p("lib"), "settlement", "--in", "Entities")
        self.assertIn("== Atlas.md", out)
        self.assertIn("no match", kbfind("find", self.p("lib"), "nothing-like-this"))
        p = subprocess.run([sys.executable, QUERY, "find", self.p("lib"), "x", "--in", "../.."], capture_output=True)
        self.assertEqual(p.returncode, 2)

    def test_toc(self):
        out = kbfind("toc", self.p("lib", "00_Status-Card.md"))
        self.assertIn("1-2 | # Status card", out)
        self.assertIn("3-46 | ## Payments |", out)
        self.assertIn("40 items", out)
        self.assertIn("| ## Projects |", out)
        self.assertIn("2 table rows", out)


PENDING = "<!-- kb:conclusions-pending -->"


class ConsolidateTest(Tmp):
    def setUp(self):
        super().setUp()
        self.topic = self.p("lib", "05_X_bill_A.md")
        write(self.p("lib", "_kb.json"), json.dumps({"schema": 1}))
        write(self.topic, '---\ntitle: "A"\noriginal: "[[Sources/05_X_bill_A.pdf]]"\n---\n\n' + PENDING +
              "\n\nBody line one.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")
        self.head = self.p("head.md")
        write(self.head, '---\ntitle: "A"\noriginal: "[[Sources/05_X_bill_A.pdf]]"\n---\n\nKey conclusions\n- one\n')
        queue = "# Consolidation queue\n\n| File | Source file | Filed | Close-read |\n| --- | --- | --- | --- |\n"
        queue += "| b.md | b.txt | 2026-10-02 10:00 | no |\n| a.md | a.txt | 2026-10-01 10:00 | yes |\n"
        write(self.p("work", "_Consolidation-Queue.md"), queue)
        write(self.p("lib", "_Consolidation-Queue.md"), queue)

    def test_fill_keeps_body(self):
        out = self.p("out", "05_X_bill_A.md")
        os.makedirs(self.p("out"))
        self.assertIn("body unchanged", run("consolidate.py", "fill", self.topic, self.head, out).stdout)
        text = read(out)
        self.assertNotIn(PENDING, text)
        self.assertIn("Key conclusions\n- one\n\nBody line one.", text)
        self.assertTrue(text.endswith("| 1 | 2 |\n"))
        p = run("consolidate.py", "fill", self.topic, self.head, out, check=False)
        self.assertEqual(p.returncode, 3)  # output exists

    def test_fill_refusals(self):
        os.makedirs(self.p("out"))
        write(self.p("nomark.md"), "---\ntitle: x\n---\n\nbody\n")
        p = run("consolidate.py", "fill", self.p("nomark.md"), self.head, self.p("out", "a.md"), check=False)
        self.assertIn("no pending mark", p.stdout)
        write(self.p("h2.md"), '---\ntitle: "A"\n---\n\nKey conclusions\n')
        p = run("consolidate.py", "fill", self.topic, self.p("h2.md"), self.p("out", "b.md"), check=False)
        self.assertIn("original line", p.stdout)
        write(self.p("h3.md"), "---\ntitle: A\n" + PENDING + "\n")
        p = run("consolidate.py", "fill", self.topic, self.p("h3.md"), self.p("out", "c.md"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertFalse(os.listdir(self.p("out")))

    def test_list_and_done(self):
        out = run("consolidate.py", "list", self.p("work", "_Consolidation-Queue.md"), "--limit", "1").stdout
        self.assertIn("queue: 2 files, oldest filed 2026-10-01 10:00", out)
        self.assertIn("a.md | a.txt | 2026-10-01 10:00 | close-read", out)
        self.assertNotIn("b.md |", out)
        out = run("consolidate.py", "done", self.p("work", "_Consolidation-Queue.md"), "--name", "a.md",
                  "--name", "zz.md").stdout
        self.assertIn("not in the queue: zz.md", out)
        self.assertIn("1 files still wait", out)
        self.assertNotIn("| a.md |", read(self.p("work", "_Consolidation-Queue.md")))
        p = run("consolidate.py", "done", self.p("lib", "_Consolidation-Queue.md"), "--name", "a.md", check=False)
        self.assertEqual(p.returncode, 3)


class IntakeSettingsTest(Tmp):
    def test_mode_defaults_to_fast(self):
        write(self.p("_kb.json"), json.dumps({"schema": 1}))
        cfg = kbconf.load_library(self.d)
        self.assertEqual(cfg["intake"]["mode"], "fast")
        self.assertEqual(cfg["intake"]["consolidate_files"], 10)
        self.assertEqual(cfg["names"]["consolidation_queue"], "_Consolidation-Queue.md")
        self.assertEqual(kbconf.validate({"schema": 1, "intake": {"mode": "full"}}), [])
        self.assertTrue(kbconf.validate({"schema": 1, "intake": {"mode": "slow"}}))


if __name__ == "__main__":
    unittest.main()


def id_number(base="11010519900307123"):
    """A made-up 18-digit ID number with a valid check digit, built here so no such number is written down."""
    total = sum(int(c) * w for c, w in zip(base, kbconf.ID_WEIGHTS))
    return base + "10X98765432"[total % 11]


def card_number(prefix="6222" + "0" * 14):
    return next(prefix + d for d in "0123456789" if kbconf.luhn_ok(prefix + d))


LABEL = "口" + "令"  # a password label, joined here so the sample line is no real field


class ClassATest(Tmp):
    def test_scan(self):
        text = (f"id {id_number()} card {card_number()}\norder 1234567890123456\n"
                "grouped 6222 0210 0000 0000 001\n" + LABEL + ": abc123; code: 2026; 验证码=****56\n"
                "phone 138" + "0" * 8 + "\n")
        hits = kbconf.scan_class_a(text)
        kinds = [(no, kind) for no, kind, _ in hits]
        self.assertIn((1, "ID number"), kinds)
        self.assertIn((1, "card number"), kinds)
        self.assertIn((2, "16-19 digits (order or serial number?)"), kinds)
        self.assertIn((3, "number in groups of four"), kinds)
        self.assertIn((4, LABEL + " not masked"), kinds)
        self.assertEqual(len([k for k in kinds if k[0] == 4]), 1)  # the starred code passes
        self.assertFalse([k for k in kinds if k[0] == 5])  # 11 digits are not class-A here
        self.assertEqual(hits[0][2], "*" * 14 + id_number()[-4:])
        self.assertEqual(len([k for k in kinds if k[0] == 1]), 2)  # the ID is not reported again as digits

    def test_cli(self):
        write(self.p("a.md"), f"x {card_number()}\n")
        write(self.p("b.md"), "clean\n")
        p = run("kbconf.py", "scan-a", self.p("a.md"), self.p("b.md"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("a.md:1: card number: ", p.stdout)
        self.assertNotIn(card_number(), p.stdout)
        self.assertIn("no class-A", run("kbconf.py", "scan-a", self.p("b.md")).stdout)


class MetaApplyTest(Tmp):
    def test_apply_terms_and_mask(self):
        body = self.p("work", "body_1.md")
        write(body, f"# Plan\n\nAtlass starts. Atlass ends.\n\n## Money\n\nCard {card_number()} here.\n")
        write(self.p("work", "fixes_1.tsv"), f"3\tAtlass\tAtlas\t2\n7\t{card_number()}\tmask\n")
        out = run("meta.py", "apply", body, self.p("work", "fixes_1.tsv")).stdout
        self.assertIn("Atlass -> Atlas -> Plan", out)
        self.assertIn("line 7: masked, last 4 kept -> Money", out)
        self.assertNotIn(card_number(), out)
        text = read(body)
        self.assertIn("Atlass starts. Atlas ends.", text)
        self.assertIn("Card " + "*" * 15 + card_number()[-4:] + " here.", text)

    def test_apply_refuses_without_change(self):
        body = self.p("work", "body_1.md")
        write(body, "one\ntwo\n")
        write(self.p("f.tsv"), "1\tone\t1\n2\tthree\t3\n9\ttwo\t2\n")
        p = run("meta.py", "apply", body, self.p("f.tsv"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("row 2: line 2 does not hold the original wording", p.stdout)
        self.assertIn("row 3: line 9 is outside the body", p.stdout)
        self.assertEqual(read(body), "one\ntwo\n")
        write(self.p("lib", "_kb.json"), "{}")
        write(self.p("lib", "b.md"), "one\n")
        p = run("meta.py", "apply", self.p("lib", "b.md"), self.p("f.tsv"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("inside a library root", p.stdout)


class PrepBatchTest(Tmp):
    def setUp(self):
        super().setUp()
        self.lib = self.p("lib")
        write(os.path.join(self.lib, "_kb.json"), json.dumps({"schema": 1, "label": "Work", "timezone": "UTC",
                                                             "language": "en", "metadata": "text"}))
        write(os.path.join(self.lib, "00_Spec.md"), SPEC_EN)
        write(os.path.join(self.lib, "00_Status-Card.md"), "# Status\n\n1. Atlas goes live in May.\n2. Other.\n")
        write(os.path.join(self.lib, "01_File-Index.md"),
              "# File index\n\nFile name | Source file\n--- | ---\n02_Ops_memo_Old.md | old.docx\n")
        write(os.path.join(self.lib, "02_Ops_memo_Old.md"), "old\n")
        self.work = self.p("work")
        self.src = self.p("material")
        write(os.path.join(self.src, "a.md"), "# Kickoff\n\nProject Atlas and the Payments Gateway. Atlass.\n")
        write(os.path.join(self.src, "b.txt"), "Budget notes, nothing else.\n")

    def test_scan_batch(self):
        out = run("prep.py", "scan-batch", os.path.join(self.src, "a.md"), os.path.join(self.src, "b.txt"),
                  "--library", self.lib, "--work", self.work, "--start", "3").stdout
        self.assertIn("=== Item 3: a.md ===", out)
        self.assertIn("=== Item 4: b.txt ===", out)
        self.assertIn("Atlass -> Atlas: 1 lines", out)
        self.assertIn("  Project Atlas (Project Atlas): 1x", out)  # Atlass is no hit for Atlas, PA none in Payments
        self.assertIn("  Payments Gateway (Payments Gateway): 1x", out)
        self.assertIn("status card lines naming them: 1 (lines 3)", out)
        self.assertIn("items: 2 | ready: 2 | duplicate uploads: 0", out)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "body_3.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.work, "body_4.md")))

    def test_file_batch(self):
        run("prep.py", "scan-batch", os.path.join(self.src, "a.md"), os.path.join(self.src, "b.txt"),
            "--library", self.lib, "--work", self.work)
        write(os.path.join(self.work, "head_1.md"), "Date: 2026-10-01\n\nKey conclusions\n- Atlas starts (source: Kickoff)\n")
        write(os.path.join(self.work, "head_2.md"), "Date: 2026-10-02\n")
        dec = self.p("work", "decisions.json")
        items = [{"n": 1, "partition": "02", "topic": "Ops", "type": "memo", "title": "Kickoff", "orig": "a.md",
                  "source": os.path.join(self.src, "a.md")},
                 {"n": 2, "partition": "02", "topic": "Ops", "type": "memo", "title": "Old", "orig": "b.txt"}]
        write(dec, json.dumps(items))
        out = self.p("work", "out_b1")
        p = run("prep.py", "file-batch", dec, "--library", self.lib, "--work", self.work, "--out", out, check=False)
        self.assertEqual(p.returncode, 3)  # item 2 hits an existing name: nothing is written
        self.assertIn("item 2: 02_Ops_memo_Old.md is in the index", p.stdout)
        self.assertFalse(os.path.exists(out))
        items[1]["same_version"] = True
        write(dec, json.dumps(items))
        p = run("prep.py", "file-batch", dec, "--library", self.lib, "--work", self.work, "--out", out)
        self.assertIn("+ 02_Ops_memo_Kickoff.md (from a.md)", p.stdout)
        self.assertIn("~ 02_Ops_memo_Old.md (from b.txt, same-name new version)", p.stdout)
        self.assertIn("index: 1 added, 1 updated", p.stdout)
        topic = read(os.path.join(out, "02_Ops_memo_Kickoff.md"))
        self.assertTrue(topic.startswith("Date: 2026-10-01\n"))
        self.assertIn("Project Atlas and the Payments Gateway", topic)
        index = read(os.path.join(out, "01_File-Index.md"))
        self.assertIn("02_Ops_memo_Kickoff.md", index)
        self.assertIn("02_Ops_memo_Old.md | b.txt", index)
        self.assertNotIn("Consolidation", " ".join(os.listdir(out)))
        self.assertEqual(read(os.path.join(self.lib, "01_File-Index.md")).count("|"), 3)  # the library is untouched

    def test_file_batch_same_name_twice(self):
        run("prep.py", "scan-batch", os.path.join(self.src, "a.md"), os.path.join(self.src, "b.txt"),
            "--library", self.lib, "--work", self.work)
        for n in (1, 2):
            write(os.path.join(self.work, f"head_{n}.md"), "Date: x\n")
        items = [{"n": n, "partition": "02", "topic": "Ops", "type": "memo", "title": "Same", "orig": f"{n}"}
                 for n in (1, 2)]
        write(self.p("d.json"), json.dumps(items))
        p = run("prep.py", "file-batch", self.p("d.json"), "--library", self.lib, "--work", self.work,
                "--out", self.p("o"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("item 2: same file name as item 1", p.stdout)


class PackageClassATest(Tmp):
    def test_preview_stops_on_class_a(self):
        lib, out = self.p("lib"), self.p("out")
        write(os.path.join(lib, "_kb.json"), json.dumps({"schema": 1, "label": "Life", "timezone": "UTC",
                                                         "sensitivity": {"enabled": True, "keep_last": 4}}))
        write(os.path.join(out, "02_Money_card_A.md"), f"card {card_number()}\n")
        write(os.path.join(out, "01_File-Index.md"), "index\n")
        write(os.path.join(out, "README.txt"), "readme\n")
        plan = self.p("work", "plan.json")
        os.makedirs(os.path.dirname(plan))
        p = run("package.py", "preview", out, "--library", lib, "--plan", plan, "--in-place", check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("Class-A candidate: 02_Money_card_A.md line 1: card number", p.stdout)
        self.assertNotIn(card_number(), p.stdout)
        self.assertFalse(os.path.exists(plan))
        p = run("package.py", "preview", out, "--library", lib, "--plan", plan, "--in-place", "--class-a-reviewed")
        self.assertTrue(os.path.isfile(plan))


class KbAskTest(Tmp):
    def setUp(self):
        super().setUp()
        lib = self.lib = self.p("lib")
        write(os.path.join(lib, "_kb.json"), json.dumps({"schema": 1, "label": "Work"}))
        write(os.path.join(lib, "00_Spec.md"), SPEC_EN)
        write(os.path.join(lib, "00_Status-Card.md"), "# Status card\n\n## Projects\n\n"
              "1. Atlas launches in May (basis: 05_Ops_minutes_Kickoff.md)\n2. Payments run daily.\n")
        write(os.path.join(lib, "01_File-Index.md"), "# File index\n\nFile name | Source file\n--- | ---\n"
              "05_Ops_minutes_Kickoff.md | kickoff.docx\n05_Ops_memo_Other.md | other.docx\n")
        write(os.path.join(lib, "01_Open-Items.md"), "# Open items\n\n1. Atlass budget not decided.\n")
        write(os.path.join(lib, "05_Ops_minutes_Kickoff.md"), "# Kickoff\n\nThe Atlas team met.\n\n## Budget\n\nNo budget yet.\n")
        write(os.path.join(lib, "05_Ops_memo_Other.md"), "# Other\n\nPA review of Atlas, Atlas and Atlas.\n")
        write(os.path.join(lib, "05_Ops_memo_Unrelated.md"), "# Payments\n\nNothing about the project.\n")
        write(os.path.join(lib, "Entities", "Project Atlas.md"), "# Project Atlas\n")
        write(os.path.join(lib, "Quick-Notes", "20261001-0900_note.md"), "Quick note\nZebra crossing idea\n")
        write(os.path.join(lib, "README.md"), "Atlas\n")

    def test_ask_expands_and_orders(self):
        out = kbfind("ask", self.lib, "--q", "Project Atlas")
        self.assertIn("keyword 1: Project Atlas | Atlas | PA  [added: Atlas (Table E: Project Atlas); "
                      "PA (Table E: Project Atlas)]", out)
        self.assertIn("== status_card: 00_Status-Card.md | 1 blocks", out)
        self.assertIn("1. Atlas launches in May", out)
        self.assertIn("== index: 01_File-Index.md | 0 blocks", out)
        self.assertIn("== open_items: 01_Open-Items.md | 0 blocks", out)  # Atlass is no whole-word Atlas
        self.assertIn("== source files | 3 searched | 2 with hits", out)
        # the file the status card names comes first, though the other has more hits
        self.assertLess(out.index("= 05_Ops_minutes_Kickoff.md"), out.index("= 05_Ops_memo_Other.md"))
        self.assertIn("named in the status card or index", out)
        self.assertNotIn("Unrelated", out)  # "PA" is not found inside "Payments"
        self.assertNotIn("README", out)
        self.assertIn("entity pages for these keywords: Entities/Project Atlas.md", out)
        self.assertNotIn("quick notes", out)

    def test_ask_old_form_all_and_notes_fallback(self):
        out = kbfind("ask", self.lib, "--q", "Atlass")
        self.assertIn("keyword 1: Atlass | Atlas | Project Atlas | PA  [added: Atlas (standard form, Table B); "
                      "Project Atlas (Table E: Project Atlas)", out)  # the standard form brings its aliases
        self.assertIn("1. Atlass budget not decided.", out)
        out = kbfind("ask", self.lib, "--q", "Atlas", "--q", "budget", "--all")
        self.assertIn("== source files | 3 searched | 0 with hits", out)
        out = kbfind("ask", self.lib, "--q", "zebra")
        self.assertIn("== quick notes (nothing in the library itself) | 1 with hits", out)
        self.assertIn("Quick-Notes/20261001-0900_note.md (quick note, not yet filed)", out)
        self.assertIn("no match in the library", out)

    def test_ask_output_cap(self):
        out = kbfind("ask", self.lib, "--q", "Atlas", "--max-chars", "400")
        self.assertIn("not shown (output cap)", out)


CARD = """# 状态卡
最后更新：2026-10-01

一、项目
示例项目：五月上线（依据：05_示例_纪要_启动会.md）
承接方：示例组
二、口径
统计口径：按自然月
统计口径：按自然月
"""


class CardPatchTest(Tmp):
    def patch(self, ops, check=True, **kw):
        write(self.p("old.md"), kw.get("old", CARD))
        write(self.p("patch.json"), json.dumps(ops, ensure_ascii=False))
        args = ["apply", self.p("old.md"), self.p("patch.json"), "--out", self.p("out", "new.md")]
        return run("card_patch.py", *args + (["--check"] if kw.get("card_check") else []), check=check)

    def test_every_operation_and_change_list(self):
        p = self.patch([
            {"op": "replace", "old": "示例项目：五月上线（依据：05_示例_纪要_启动会.md）",
             "new": "示例项目：六月上线（依据：05_示例_纪要_复盘会.md）"},
            {"op": "delete", "old": "承接方：示例组", "reason": "已移交"},
            {"op": "insert_after", "anchor": "二、口径", "new": "汇总口径：按季度"},
            {"op": "insert_before", "anchor": "二、口径", "new": "示例子项：待定\n示例子项二：待定"},
            {"op": "set_field", "field": "最后更新", "value": "2026-10-25"},
        ], card_check=True)
        self.assertIn("patched: 1 replaced, 1 deleted, 2 inserted, 1 fields", p.stdout)
        self.assertIn("Result: passed", p.stdout)
        new = read(self.p("out", "new.md"))
        self.assertEqual(new, "# 状态卡\n最后更新：2026-10-25\n\n一、项目\n示例项目：六月上线（依据：05_示例_纪要_复盘会.md）\n"
                              "示例子项：待定\n示例子项二：待定\n二、口径\n汇总口径：按季度\n统计口径：按自然月\n统计口径：按自然月\n")
        changes = read(self.p("out", "new.changes.txt"))
        self.assertIn("Item: 示例项目：五月上线（依据：05_示例_纪要_启动会.md） -> 示例项目：六月上线", changes)
        self.assertIn("Delete item: 承接方：示例组 (已移交)", changes)
        self.assertIn("Field 最后更新: 2026-10-01 -> 2026-10-25", changes)

    def test_refusals_write_nothing(self):
        p = self.patch([
            {"op": "replace", "old": "统计口径：按自然月", "new": "x"},
            {"op": "replace", "old": "不存在的一行", "new": "x"},
            {"op": "delete", "old": "承接方：示例组"},
            {"op": "replace", "old": "一、项目\n示例项目：五月上线（依据：05_示例_纪要_启动会.md）", "new": "y"},
            {"op": "insert_after", "anchor": "一、项目", "new": "z"},
            {"op": "set_field", "field": "版本", "value": "v2"},
        ], check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("change 1 (replace): found 2 times", p.stdout)
        self.assertIn("change 2 (replace): not found", p.stdout)
        self.assertIn("change 3 (delete): a deletion needs a reason", p.stdout)
        self.assertIn("change 5 is anchored on lines that change 4 replaces or deletes", p.stdout)
        self.assertIn("change 6 (set_field): no line starts with 版本:", p.stdout)
        self.assertFalse(os.path.exists(self.p("out", "new.md")))

    def test_check_catches_an_unexplained_loss(self):
        p = self.patch([{"op": "replace", "old": "承接方：示例组", "new": "承接方：示例二组"}], card_check=True)
        self.assertIn("Result: passed", p.stdout)  # the replaced line is explained by the change list
        # a line the patch never touched but that is gone (here: the old file held one more) still fails
        write(self.p("longer.md"), CARD + "附注：保留此行\n")
        p = run("card_check.py", self.p("longer.md"), self.p("out", "new.md"), "--changes",
                self.p("out", "new.changes.txt"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("1 unexplained losses", p.stdout)

    def test_trailing_spaces_and_final_newline(self):
        old = "a  \nb\nc"
        p = self.patch([{"op": "replace", "old": "a", "new": "A"}], old=old)
        self.assertEqual(read(self.p("out", "new.md")), "A\nb\nc")

    def test_refuses_output_in_library(self):
        write(self.p("lib", "_kb.json"), "{}")
        write(self.p("old.md"), CARD)
        write(self.p("patch.json"), "[]")
        p = run("card_patch.py", "apply", self.p("old.md"), self.p("patch.json"), "--out",
                self.p("lib", "00_x.md"), check=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("inside a library root", p.stdout)


SPEC_ZH_TEXT = """00 整理规范（v1.2）

本规范定义表A、表B、表E，见下文。修订说明：v1.1 起在表E登记实体。

一、表A　分区与议题

01　汇总：状态卡、索引。
02　示例分区：示例议题甲、示例议题乙。
03　兜底分区：其他。

二、表B　术语修正

原写法 → 规范写法 → 备注
旧称甲 → 新称甲 → 示例
旧称乙 → 新称乙 → 示例

三、表E　实体

列：名称｜类型｜别名｜核心
类型可选：项目、系统。

示例系统｜系统｜示例系统简称;SYS｜是
另一系统｜系统｜无｜否

四、表F　取值过滤
空值写法：无、暂无。
"""


class SpecTableTest(Tmp):
    def test_titles_arrows_lead_in_and_placeholders(self):
        self.assertEqual(kbconf.term_pairs(SPEC_ZH_TEXT), [("旧称甲", "新称甲"), ("旧称乙", "新称乙")])
        self.assertEqual(kbconf.entity_list(SPEC_ZH_TEXT),
                         [("示例系统", ["示例系统简称", "SYS"]), ("另一系统", [])])  # "无" is no alias
        header, rows = kbconf.spec_table(SPEC_ZH_TEXT, "E")
        self.assertEqual(header, ["名称", "类型", "别名", "核心"])  # "列：" dropped
        self.assertEqual(len(rows), 2)  # the note between header and rows is skipped
        self.assertIsNone(kbconf.spec_table(SPEC_ZH_TEXT, "A"))  # running text, no rows
        self.assertEqual([ln for ln in kbconf.spec_section(SPEC_ZH_TEXT, "A") if ln.strip()][0], "01　汇总：状态卡、索引。")

    def test_full_width_and_markdown_tables(self):
        spec = "一、表A　分区\n\n分区号｜分区名｜议题\n01｜汇总｜索引\n02｜示例｜示例议题\n\n二、表B　术语\n\n原写法｜规范写法\n暂无条目。\n"
        self.assertEqual(kbconf.spec_table(spec, "A")[1], [["01", "汇总", "索引"], ["02", "示例", "示例议题"]])
        self.assertEqual(kbconf.term_pairs(spec), [])  # header only: an empty table, not a missing one
        self.assertEqual(kbconf.entity_list(SPEC_EN), [("Project Atlas", ["Atlas", "PA"]), ("Payments Gateway", [])])
        self.assertIsNone(kbconf.spec_table("Only Table B is mentioned here, in a sentence.\nA | B\n", "B"))

    def test_title_with_bracketed_note(self):
        spec = "表A　分区\n01｜汇总\n\n表C　存疑项（规范层面、待定）\n1. 示例存疑\n\n见表C、表D的说明。\n"
        self.assertEqual([ln for ln in kbconf.spec_section(spec, "C") if ln.strip()][0], "1. 示例存疑")
        self.assertIsNone(kbconf.spec_section("见表C、表D的说明。\n", "C"))  # a sentence stays no title

    def test_spec_brief_leaves_out_revision_notes(self):
        spec = ("00 整理规范（v1.2）\n修订说明：2026-01-01 新增表E。\n修订说明：2026-02-01 调整表B。\n\n"
                "一、表A　分区\n01　汇总\n\n二、表B　术语\n旧称甲 → 新称甲\n\n表述规范\n全程中文。\n\n"
                "本次修订说明（v1.2）\n\n一、表B新增一条。\n　细节一行。\n\n修订历史（摘要）\n\n一、v1.0 建立。\n\n"
                "最后更新：2026-02-01\n")
        text, skip = kbconf.spec_brief(spec)
        self.assertEqual(skip, [(2, 3), (14, 21)])
        self.assertNotIn("修订", text.replace("[revision notes", ""))
        self.assertIn("[revision notes, lines 2-3 (2 lines), left out", text)
        self.assertIn("表述规范\n全程中文。", text)
        self.assertIn("最后更新：2026-02-01", text)
        self.assertTrue(text.endswith("[tables found by title: A, B; not found: C, D, E, F]"))
        self.assertIn("本次修订说明", kbconf.spec_brief(spec, with_revisions=True)[0])
        write(self.p("lib", "_kb.json"), json.dumps({"schema": 1, "label": "示例库", "timezone": "UTC"}))
        write(self.p("lib", "00_Spec.md"), spec)
        out = run("kbconf.py", "spec", self.p("lib")).stdout
        self.assertIn("lines 14-21 (8 lines), left out", out)

    def test_meta_terms_on_arrow_table(self):
        write(self.p("spec.md"), SPEC_ZH_TEXT)
        write(self.p("body.md"), "# 记录\n\n旧称甲已停用。\n")
        out = run("meta.py", "terms", self.p("spec.md"), self.p("body.md")).stdout
        self.assertIn("旧称甲 -> 新称甲: 1 lines", out)
