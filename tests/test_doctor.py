"""Environment diagnosis is read-only and does not infer remote authorization."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "kb-ingest" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("kbdoctor", SCRIPTS / "kbdoctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "_kb.json").write_text(json.dumps({"schema": 1}), encoding="utf-8")
        (self.root / "_kb-params.md").write_text("parameters", encoding="utf-8")

    def test_optional_and_required_pdf(self):
        with patch.object(doctor.shutil, "which", side_effect=lambda name: "/bin/git" if name == "git" else None):
            self.assertFalse(any(s == "error" for s, _ in doctor.diagnose(self.root)))
            self.assertEqual(sum(s == "error" for s, _ in doctor.diagnose(self.root, True)), 3)

    def test_bad_config_and_missing_params(self):
        (self.root / "_kb.json").write_text("[]", encoding="utf-8")
        (self.root / "_kb-params.md").unlink()
        self.assertGreaterEqual(sum(s == "error" for s, _ in doctor.diagnose(self.root)), 2)

    def test_no_remote_requests_and_no_writes(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        original = doctor.subprocess.run
        calls = []

        def record(args, **kwargs):
            calls.append(args)
            return original(args, **kwargs)

        with patch.object(doctor.subprocess, "run", side_effect=record):
            doctor.diagnose(self.root)
        self.assertTrue(all("fetch" not in c and "push" not in c and "ls-remote" not in c for c in calls))
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
