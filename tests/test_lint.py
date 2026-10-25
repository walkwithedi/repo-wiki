"""Tests for the health check on disk (kb-ingest scripts/lint.py). Standard library only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "kb-ingest", "scripts")
sys.path.insert(0, SCRIPTS)
import kbconf  # noqa: E402

SPEC = """# 00 规范（v1.0）

一、表A　分区与议题

01　汇总：状态卡、索引。
02　示例分区：示例议题、会议纪要。
03　兜底分区：其他。

二、表E　实体

名称｜类型｜别名｜核心
示例系统｜系统｜示例系统简称｜是
示例平台｜系统｜无｜否
示例-平台｜系统｜无｜否
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def topic(fields, body="正文。\n"):
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n\n" + body


def card_number(prefix="6222" + "0" * 14):
    return next(prefix + d for d in "0123456789" if kbconf.luhn_ok(prefix + d))


class LintTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        d = self.d = self._t.name
        lib = self.lib = os.path.join(d, "lib")
        write(os.path.join(lib, "_kb.json"), json.dumps({
            "schema": 1, "label": "示例库", "language": "zh", "timezone": "+08:00", "metadata": "yaml",
            "sensitivity": {"enabled": True, "keep_last": 4}, "partitions": {"max": 3, "topic_start": 2, "fallback": "03"},
            "names": {"spec": "00_规范.md", "status_card": "00_状态卡.md", "index": "01_索引.md",
                      "entities_dir": "实体", "notes_dir": "随手记"}}, ensure_ascii=False))
        write(os.path.join(lib, "_kb-params.md"), "# 参数\n")
        write(os.path.join(lib, "00_规范.md"), SPEC)
        ok = {"分区": '"02"', "议题": '"示例议题"', "文档日期": "2026-09-01", "涉及系统": '["[[示例系统]]"]'}
        write(os.path.join(lib, "02_示例议题_纪要_九月例会.md"), topic(ok))
        extra = [f"02_示例议题_纪要_例会{k}.md" for k in range(1, 10)]  # so that 文档日期 is in 90% of the files
        for name in extra:
            write(os.path.join(lib, name), topic(ok))
        write(os.path.join(lib, "02_示例议题_纪要_2026-12-启动.md"), topic(dict(ok, 文档日期="2026-09-02")))
        write(os.path.join(lib, "02_示例议题_纪要_缺日期.md"),
              topic({"分区": '"02"', "议题": '"示例议题"', "涉及系统": '["[[未登记系统]]"]'}))
        write(os.path.join(lib, "03_不存在议题_纪要_格式.md"),
              topic({"分区": '"02"', "议题": '"不存在议题"', "文档日期": "2026/9/3", "涉及系统": "[]"}))
        write(os.path.join(lib, "02_示例议题_纪要_无属性.md"), f"没有属性区，卡号 {card_number()}。\n")
        write(os.path.join(lib, "01_索引.md"), "# 索引\n条目数：4\n\n文件名｜原始文件名\n"
              "02_示例议题_纪要_九月例会.md｜a.docx\n02_示例议题_纪要_2026-12-启动.md｜b.docx\n"
              "02_示例议题_纪要_缺日期.md｜c.docx\n02_已删除.md｜d.docx\n" + "".join(f"{n}｜x.docx\n" for n in extra))
        write(os.path.join(lib, "00_状态卡.md"), "# 状态卡\n最后更新：2026-09-05\n\n"
              "1. 示例系统九月上线（依据：[[02_示例议题_纪要_九月例会]]）\n"
              "2. 示例平台下线（依据：会议口头通知）\n3. 示例链接（依据：[[02_不存在的文件]]）\n")
        write(os.path.join(lib, "实体", "示例系统.md"), '---\ntype: "entity"\ncore: true\n---\n\n# 示例系统\n')
        write(os.path.join(lib, "实体", "孤立页面.md"), "# 孤立页面\n")
        write(os.path.join(lib, "随手记", "20260901-0900_示例.md"), "随手记\n")
        write(os.path.join(lib, "_运行日志_旧.txt"), "x\n")
        write(os.path.join(lib, "02_示例_纪要_old_旧20260101120000.md"), "x\n")
        write(os.path.join(lib, "README.md"), "# 仓库说明\n")
        self.work = os.path.join(d, "work")

    def tearDown(self):
        self._t.cleanup()

    def lint(self, *extra):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "lint.py"), self.lib, "--work", self.work, "--all",
                            *extra], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_report(self):
        out = self.lint()
        self.assertIn("scope: 14 of 14 topic files, all files", out)
        self.assertIn("1. Stray files: 2", out)  # the run log and the old copy
        self.assertNotIn("README.md", out.split("2. ")[0])
        self.assertIn("2. Same-name copies: not applicable", out)
        self.assertIn("3. Table E and entity pages: 7", out)
        self.assertIn("no identity line: 实体/示例系统.md", out)
        self.assertIn("related files out of date: 实体/示例系统.md", out)
        self.assertIn("no page: 示例平台", out)
        self.assertIn("no Table E row: 实体/孤立页面.md", out)
        self.assertIn("02_示例议题_纪要_无属性.md: no front matter", out)
        self.assertIn("02_示例议题_纪要_缺日期.md: missing 文档日期", out)
        self.assertIn("02_示例议题_纪要_缺日期.md: links outside Table E: 未登记系统", out)
        self.assertIn("03_不存在议题_纪要_格式.md: 文档日期 not an ISO date: 2026/9/3", out)
        self.assertIn("03_不存在议题_纪要_格式.md: partition 02 differs from the file name", out)
        self.assertIn("03_不存在议题_纪要_格式.md: topic not in Table A: 不存在议题", out)
        self.assertIn("5. Suspicious dates: 1", out)
        self.assertIn("02_示例议题_纪要_2026-12-启动.md: name 2026-12, document date 2026-09-02", out)
        self.assertIn("6. Basis lines: 1 not linked, 1 broken", out)
        self.assertIn("status card line 6: 02_不存在的文件", out)
        self.assertIn("7. Overviews possibly stale: ", out)
        self.assertIn("8. Index mismatches: 3", out)
        self.assertIn("row without file: 02_已删除.md", out)
        self.assertIn("not in the index: 02_示例议题_纪要_无属性.md", out)
        self.assertIn("9. Settings: consistent", out)
        self.assertIn("示例平台 / 示例-平台", out)
        self.assertIn("high: only case, spaces, hyphens or punctuation differ", out)
        self.assertIn("11. Quick-note backlog: 1 notes, oldest 2026-09-01", out)
        self.assertIn("12. Consolidation backlog: no queue", out)
        self.assertIn("13. Status-card values: 1 items checked", out)  # item 3 links a missing file (check 6)
        self.assertIn("14. Class-A candidates: 1", out)
        self.assertNotIn(card_number(), out)

    def test_settings_mismatch_and_scope(self):
        with open(os.path.join(self.lib, "_kb.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["partitions"] = {"max": 9, "topic_start": 2, "fallback": "07"}
        write(os.path.join(self.lib, "_kb.json"), json.dumps(cfg, ensure_ascii=False))
        out = self.lint()
        self.assertIn("partitions.max is 9, Table A ends at 03", out)
        self.assertIn("partitions.fallback 07 is not a partition in Table A", out)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "lint.py"), self.lib, "--work", self.work, "--days", "30"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertIn("modified in the last 30 days (file time)", p.stdout)  # no git here

    def test_work_folder_outside_library(self):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "lint.py"), self.lib, "--work",
                            os.path.join(self.lib, "w")], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
