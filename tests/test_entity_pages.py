"""Tests for the related-files lists of entity pages (kb-ingest scripts/entity_pages.py). Standard library only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "kb-ingest", "scripts")

PAGE = """---
类型: "实体"
实体类型: "系统"
核心: false
aliases: ["示例简称"]
---

# 示例系统

示例系统是一个虚构的业务系统。

## 相关文件

```base
filters:
  and:
    - file.hasLink(this.file)
```
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def topic(date, kind, links):
    head = f'---\n文档日期: {date}\n类型: "{kind}"\n涉及系统: {links}\n---\n\n' if date else \
        f'---\n类型: "{kind}"\n涉及系统: {links}\n---\n\n'
    return head + "正文。\n"


def run(*args, check=True):
    p = subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding="utf-8")
    if check:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


class EntityPagesTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        d = self.d = self._t.name
        lib = self.lib = os.path.join(d, "lib")
        write(os.path.join(lib, "_kb.json"), json.dumps({
            "schema": 1, "label": "示例库", "language": "zh", "timezone": "+08:00", "metadata": "yaml",
            "names": {"spec": "00_规范.md", "index": "01_索引.md", "entities_dir": "实体"}}, ensure_ascii=False))
        write(os.path.join(lib, "00_规范.md"), "# 规范\n示例：涉及系统: [\"[[示例系统]]\"]\n")
        write(os.path.join(lib, "01_索引.md"), "# 索引\n")
        write(os.path.join(lib, "02_示例_纪要_九月.md"), topic("2026-09-01", "纪要", '["[[示例系统]]"]'))
        write(os.path.join(lib, "02_示例_方案_十月.md"), topic("2026-10-01", "方案", '["[[示例系统]]", "其他"]'))
        write(os.path.join(lib, "02_示例_清单_无日期.md"), topic("", "清单", '["[[示例系统]]"]'))
        write(os.path.join(lib, "02_示例_纪要_无关.md"), topic("2026-09-05", "纪要", "[]"))
        write(os.path.join(lib, "实体", "示例系统.md"), PAGE)
        write(os.path.join(lib, "实体", "空页.md"), "---\n类型: \"实体\"\n---\n\n# 空页\n\n空页是虚构的机构。\n")

    def tearDown(self):
        self._t.cleanup()

    def script(self, *args, check=True):
        return run(os.path.join(SCRIPTS, "entity_pages.py"), *args, check=check)

    def test_in_place_writes_list_before_bases_block(self):
        self.assertEqual(self.script(self.lib, "--check", check=False).returncode, 1)
        out = self.script(self.lib, "--in-place").stdout
        self.assertIn("updated | 实体/示例系统.md", out)
        page = read(os.path.join(self.lib, "实体", "示例系统.md"))
        expect = ("## 相关文件\n\n<!-- kb:related -->\n"
                  "- [02_示例_方案_十月](<../02_示例_方案_十月.md>)｜2026-10-01｜方案\n"
                  "- [02_示例_纪要_九月](<../02_示例_纪要_九月.md>)｜2026-09-01｜纪要\n"
                  "- [02_示例_清单_无日期](<../02_示例_清单_无日期.md>)｜清单\n"
                  "<!-- /kb:related -->\n\n```base\n")
        self.assertIn(expect, page)
        self.assertIn("示例系统是一个虚构的业务系统。\n\n## 相关文件", page)
        self.assertNotIn("00_规范", page)  # summary files are not listed
        self.assertNotIn("无关", page)
        empty = read(os.path.join(self.lib, "实体", "空页.md"))
        self.assertTrue(empty.endswith("空页是虚构的机构。\n\n## 相关文件\n\n<!-- kb:related -->\n"
                                       "暂无链接到本页的文件。\n<!-- /kb:related -->\n"))
        self.assertEqual(self.script(self.lib, "--check").returncode, 0)
        self.script(self.lib, "--in-place")
        self.assertEqual(read(os.path.join(self.lib, "实体", "示例系统.md")), page)  # stable

    def test_out_overlays_the_output(self):
        self.script(self.lib, "--in-place")
        out = os.path.join(self.d, "out")
        write(os.path.join(out, "02_示例_纪要_新到.md"), topic("2026-10-20", "纪要", '["[[空页]]"]'))
        res = self.script(self.lib, "--out", out).stdout
        self.assertIn("Result: 1 entity page(s)", res)
        page = read(os.path.join(out, "实体", "空页.md"))
        self.assertIn("- [02_示例_纪要_新到](<../02_示例_纪要_新到.md>)｜2026-10-20｜纪要\n", page)
        self.assertNotIn("<!-- kb:related -->\n暂无", page)
        self.assertNotIn("新到", read(os.path.join(self.lib, "实体", "空页.md")))  # library untouched

    def test_package_preview_in_place_delivers_changed_pages(self):
        self.script(self.lib, "--in-place")
        out = os.path.join(self.d, "out")
        write(os.path.join(out, "02_示例_纪要_新到.md"), topic("2026-10-20", "纪要", '["[[示例系统]]"]'))
        write(os.path.join(out, "README.txt"), "说明\n")
        write(os.path.join(out, "01_索引.md"), "# 索引\n02_示例_纪要_新到.md\n")
        plan = os.path.join(self.d, "work", "plan.json")
        os.makedirs(os.path.dirname(plan))
        res = run(os.path.join(SCRIPTS, "package.py"), "preview", out, "--library", self.lib, "--plan", plan,
                  "--in-place").stdout
        self.assertIn("= 实体/示例系统.md", res)
        self.assertNotIn("空页", res)
        run(os.path.join(SCRIPTS, "package.py"), "deliver", "--plan", plan)
        page = read(os.path.join(self.lib, "实体", "示例系统.md"))
        self.assertIn("- [02_示例_纪要_新到](<../02_示例_纪要_新到.md>)｜2026-10-20｜纪要\n", page)
        self.assertEqual(self.script(self.lib, "--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
