"""Ground-truth validation of the detectors on real, public bug sites.

``fixtures/before/`` holds each file at the commit *before* the fix was merged
(or the current upstream version when the fix is still open); ``fixtures/after/``
holds the fixed version. A detector is validated when it fires on the known
line in ``before`` and no longer fires there in ``after``.

The benchmark is small by construction (these are the cases the author found
and fixed in public); it measures that the detectors recognise what a human
recognised, not that they find everything. Run ``pytest -q`` or
``python tests/test_fixtures.py`` for the precision table.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sfradar.detectors import scan_text  # noqa: E402

FIX = ROOT / "fixtures"

# (registry id, fixture file, expected-hit substring on the flagged line, specimen PR)
GROUND_TRUTH = [
    ("SF-05", "executorch_node_visitor.py", "assert f\"Unsupported weight per channel", "pytorch/executorch#22373"),
    ("SF-06", "executorch_conv1d_to_conv2d.py", "RuntimeError(", "pytorch/executorch#22373"),
    ("SF-08", "executorch_vulkan_quantizer_utils.py", "torch.tensor(float(", "pytorch/executorch#22372"),
    ("SF-07", "neo_io-test.yml", "git ls-remote", "NeuralEnsemble/python-neo#1912"),
    ("SF-12", "mlxlm_losses.py", "mem_flags::mem_none", "ml-explore/mlx-lm#1719"),
    ("SF-04", "pyhealth_base_dataset.py", "json.dumps(", "sunlabuiuc/PyHealth#1207"),
    ("SF-09", "dlc_tracklets.py", "self.xy[", "DeepLabCut/DeepLabCut#3445"),
]


def _hits(sid: str, path: pathlib.Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [f for f in scan_text(path.name, text) if f.id == sid]


def run():
    rows = []
    for sid, fname, needle, pr in GROUND_TRUTH:
        before = FIX / "before" / fname
        after = FIX / "after" / fname
        b = _hits(sid, before)
        detected = any(needle in f.snippet for f in b)
        if after.exists():
            a = _hits(sid, after)
            still = any(needle in f.snippet for f in a)
            cleared = "yes" if not still else "NO"
        else:
            cleared = "n/a (fix not merged upstream)"
        rows.append((sid, fname, pr, "yes" if detected else "NO", len(b), cleared))
    return rows


def test_ground_truth_detected():
    for sid, fname, pr, detected, n, cleared in run():
        assert detected == "yes", f"{sid} not detected in {fname} ({pr})"


def test_fixed_versions_clear():
    for sid, fname, pr, detected, n, cleared in run():
        assert cleared in ("yes", "n/a (fix not merged upstream)"), f"{sid} still fires on fixed {fname}"


if __name__ == "__main__":
    rows = run()
    print(f"{'id':6} {'fixture':40} {'specimen':38} {'detected':9} {'hits':5} cleared-after-fix")
    for r in rows:
        print(f"{r[0]:6} {r[1]:40} {r[2]:38} {r[3]:9} {r[4]:<5} {r[5]}")
    ok = all(r[3] == "yes" for r in rows) and all(r[5].startswith(("yes", "n/a")) for r in rows)
    print("ALL OK" if ok else "FAILURES")
    sys.exit(0 if ok else 1)
