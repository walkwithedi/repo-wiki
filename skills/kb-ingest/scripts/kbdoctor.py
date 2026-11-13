#!/usr/bin/env python3
"""Read-only environment checks for a checked-out library; never tests a push or prints credentials."""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("kbdoctor")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"


def diagnose(root, require_pdf=False):
    root = os.path.realpath(root)
    rows = []
    rows.append(("ok" if sys.version_info >= (3, 9) else "error", "Python 3.9+"))
    if shutil.which("git"):
        p = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
        good = not p.returncode and os.path.realpath(p.stdout.strip()) == root
        rows.append(("ok" if good else "error", "Git working-tree root"))
        if good:
            p = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                               capture_output=True, text=True)
            rows.append(("ok" if not p.returncode else "warning", "origin configured (URL hidden)"))
    else:
        rows.append(("error", "Git missing"))
    try:
        import kbconf
        with open(os.path.join(root, "_kb.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        good = not kbconf.validate(cfg)
        rows.append(("ok" if good else "error", "library configuration"))
    except (OSError, ValueError, TypeError, AttributeError):
        rows.append(("error", "library configuration unreadable"))
    rows.append(("ok" if os.path.isfile(os.path.join(root, "_kb-params.md")) else "error", "library parameters"))
    for tool in ("pdftotext", "pdfimages", "pdfinfo"):
        rows.append(("ok" if shutil.which(tool) else ("error" if require_pdf else "warning"), tool))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--require-pdf", action="store_true")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        default=os.environ.get("LOG_LEVEL", "INFO").upper())
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT, stream=sys.stderr)
    rows = diagnose(args.root, args.require_pdf)
    for state, label in rows:
        print(f"{state}: {label}")
    print("not checked: network, authentication, push permission, skill discovery, image reading")
    failed = any(state == "error" for state, _ in rows)
    log.info("environment checks: %s", "failed" if failed else "passed")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
