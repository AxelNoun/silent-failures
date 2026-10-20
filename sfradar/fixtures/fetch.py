"""Fetch the ground-truth fixtures from upstream at pinned commits.

The fixtures are files from third-party repositories (ExecuTorch, python-neo,
mlx-lm, PyHealth, DeepLabCut), each under its own licence. They are not
vendored here: this script downloads them from GitHub at the exact commit
before and after each fix, so the benchmark stays reproducible without
redistributing anyone's code.

    python fixtures/fetch.py          # writes fixtures/before/ and fixtures/after/
    python tests/test_fixtures.py     # then runs the validation table

Only the standard library is used. Every download is checked against the
SHA-1 of the git blob recorded in MANIFEST (the same hash `git hash-object`
prints), so a moved or rewritten file is refused rather than silently used.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "MANIFEST.json").read_text(encoding="utf-8"))


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch(repo: str, commit: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (GitHub only)
        return r.read()


def main() -> int:
    bad = 0
    for entry in MANIFEST["fixtures"]:
        for side in ("before", "after"):
            spec = entry.get(side)
            if not spec:
                continue
            dest = HERE / side / entry["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = fetch(spec["repo"], spec["commit"], entry["path"])
            got = git_blob_sha1(data)
            if got != spec["blob"]:
                print(f"[fetch] {side}/{entry['file']}: blob {got[:12]} != expected {spec['blob'][:12]} — not written")
                bad += 1
                continue
            dest.write_bytes(data)
            print(f"[fetch] {side}/{entry['file']}  <- {spec['repo']}@{spec['commit'][:10]}  ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
