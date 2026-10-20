"""Scan a directory, a git URL or a single file and write ranked findings.

    python -m sfradar.scan PATH_OR_URL [--out findings.json] [--only SF-05,SF-07] [--max-files 4000]

A git URL is cloned shallowly into a temporary directory (``git clone --depth 1``).
Only text files with known extensions are read; vendored and generated trees are
skipped. Findings are ranked by confidence, then by registry id.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

from .detectors import Finding, scan_text
from .registry import BY_ID

TEXT_EXT = {".py", ".pyx", ".pxd", ".yml", ".yaml", ".sh", ".metal", ".h", ".hpp", ".cpp", ".cc", ".cu", ".mm",
            ".jinja", ".template", ".tmpl", ".cfg", ".toml"}
SKIP_DIRS = {".git", "node_modules", "build", "dist", "site-packages", "__pycache__", "third_party", "third-party",
             "vendor", "vendored", ".venv", "venv", "_deps", "external"}
CONF_RANK = {"high": 0, "medium": 1, "low": 2}


def iter_files(root: pathlib.Path, max_files: int):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = pathlib.Path(dirpath) / fn
            if p.suffix in TEXT_EXT or fn == "Makefile":
                n += 1
                if n > max_files:
                    return
                yield p


def scan_path(target: str, only: list[str] | None = None, max_files: int = 4000) -> dict:
    tmp = None
    if target.startswith(("http://", "https://", "git@")):
        tmp = tempfile.mkdtemp(prefix="sfradar-")
        subprocess.run(["git", "clone", "--depth", "1", "--quiet", target, tmp], check=True, timeout=600)
        root = pathlib.Path(tmp)
    else:
        root = pathlib.Path(target)
    findings: list[Finding] = []
    files_scanned = 0
    try:
        paths = [root] if root.is_file() else list(iter_files(root, max_files))
        for p in paths:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            files_scanned += 1
            rel = str(p.relative_to(root)) if root.is_dir() else p.name
            findings.extend(scan_text(rel, text, only))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    findings.sort(key=lambda f: (CONF_RANK[f.confidence], f.id, f.path, f.line))
    by_id = Counter(f.id for f in findings)
    return {
        "target": target,
        "files_scanned": files_scanned,
        "summary": {k: {"count": v, "name": BY_ID[k].name_en if k in BY_ID else k} for k, v in sorted(by_id.items())},
        "findings": [f.to_dict() for f in findings],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma-separated registry ids")
    ap.add_argument("--max-files", type=int, default=4000)
    ap.add_argument("--all", action="store_true", help="include low-confidence findings (hidden by default)")
    a = ap.parse_args(argv)
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    report = scan_path(a.target, only, a.max_files)
    if not a.all:
        hidden = sum(1 for f in report["findings"] if f["confidence"] == "low")
        report["findings"] = [f for f in report["findings"] if f["confidence"] != "low"]
        report["hidden_low_confidence"] = hidden
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
        print(f"{report['files_scanned']} files, {len(report['findings'])} findings -> {a.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
