# sfradar — Silent Failures Radar

Static screening for the bugs that don't crash but falsify results in scientific and ML code. Each detector implements one entry of the **Silent Failures Registry** (`sfradar/registry.py`, 20 entries) and is anchored to a real, public specimen: a pull request where the pattern was found and fixed.

It is a radar, not a judge: it ranks where a person should look first. Low-confidence hits are hidden by default.

```bash
python sfradar-cli.py path/or/git-url [--out findings.json] [--only SF-05,SF-07] [--all]
python fixtures/fetch.py             # pull the ground-truth files at pinned commits
python tests/test_fixtures.py        # ground-truth validation table
```

No dependencies beyond the Python standard library (3.10+). A git URL is cloned shallowly into a temporary directory and deleted afterwards.

## Detectors

| Id | Class | Method | Confidence | Specimen |
| --- | --- | --- | --- | --- |
| SF-01 | grouped-entity leakage across splits (random split in a file that names patient/subject/session ids) | regex + context | low | PyHealth #1187 |
| SF-04 | non-injective / unstable cache key (`json.dumps(..., default=str)`) | AST | medium | PyHealth #1207 |
| SF-05 | assertion that cannot fail (`assert f"..."`, `assert (x, msg)`) | AST | high | executorch #22373 |
| SF-06 | exception constructed but never raised (`ValueError(...)` as a statement) | AST | high | executorch #22373 |
| SF-07 | CI step green on failure (`echo "k=$(cmd)" >> $GITHUB_OUTPUT`, `continue-on-error`, `\|\| true`) | regex | high / low | python-neo #1912 |
| SF-08 | dtype dropped when lifting a scalar (`torch.tensor(float(x))`) | regex | medium | executorch #22372 |
| SF-09 | in-place write into a DataFrame view (`.values[...] =`, or a variable derived from `.values`/`.to_numpy()` later written) | regex + AST taint | medium | DeepLabCut #3445 |
| SF-10 | unseeded randomness with no seed call in the file | regex + context | low | kinoscope |
| SF-12 | `threadgroup_barrier(mem_flags::mem_none)` around shared-memory exchange | regex | medium | mlx-lm #1719 |
| SF-13 | `metal::fast::exp/log` on unbounded arguments | regex | low | mlx-lm #1719 |
| SF-15 | float constants formatted with fixed precision in code generators | regex | low | brian2 #1891 |
| SF-18 | broad `except` that only passes | AST | medium | PyHealth #1174 |
| SF-19 | mutable default argument (shared state across calls) | AST | medium | PyHealth #1203 |

Registry entries SF-02, SF-03, SF-11, SF-14, SF-16, SF-17, SF-20 are documented but **manual**: no static pattern is reliable enough, so they live in the audit checklist, not in the radar.

## Validation (2026-10-20)

Ground truth = the bug sites the author found and fixed in public. For each, the file at the commit *before* the fix (or current upstream when the fix is still open) and the file *after*. The files are not vendored: `python fixtures/fetch.py` downloads them from GitHub at the pinned commits listed in `fixtures/MANIFEST.json` and verifies each git blob SHA-1.

| Id | Fixture (before the fix) | Specimen | Detected | Clears after fix |
| --- | --- | --- | --- | --- |
| SF-05 | executorch `backends/xnnpack/operators/node_visitor.py` | pytorch/executorch#22373 | yes | yes |
| SF-06 | executorch `backends/samsung/_passes/conv1d_to_conv2d.py` | pytorch/executorch#22373 | yes | yes |
| SF-08 | executorch `backends/vulkan/quantizer/vulkan_quantizer_utils.py` | pytorch/executorch#22372 | yes | yes |
| SF-07 | python-neo `.github/workflows/io-test.yml` | NeuralEnsemble/python-neo#1912 | yes | yes |
| SF-12 | mlx-lm `mlx_lm/tuner/losses.py` | ml-explore/mlx-lm#1719 | yes | yes (fix branch) |
| SF-04 | PyHealth `pyhealth/datasets/base_dataset.py` (still on master) | sunlabuiuc/PyHealth#1207 | yes | n/a, fix not merged |
| SF-09 | DeepLabCut `deeplabcut/refine_training_dataset/tracklets.py` | DeepLabCut/DeepLabCut#3445 | yes | yes |

7/7 detected, 6/6 cleared on the fixed versions. **Control**: `AxelNoun/discoursekit` (344 tests, mypy strict) → 0 findings at any confidence.

Field run on six live repositories (default branches, 2026-10-20), high + medium only:

| Repository | Files | High | Medium | Hidden low | Notes |
| --- | --- | --- | --- | --- | --- |
| NeuralEnsemble/python-neo | 268 | 7 | 13 | 69 | the 7 high hits are exceptions built and never raised (SF-06) in core modules; confirmed by reading, being reproduced before they are reported upstream — file-level detail withheld until the issue is open |
| sunlabuiuc/PyHealth | 643 | 0 | 27 | 201 | 11 × SF-04 (`default=str` cache keys, the open #1207), 1 × SF-08, 7 × SF-18, 8 × SF-19 |
| brian-team/brian2 | 373 | 0 | 7 | 23 | SF-18, SF-19; SF-15 ×12 (low) in the code generators |
| catalystneuro/neuroconv | 528 | 0 | 4 | 16 | 1 × SF-09 (write into a `.values` view), to be reproduced then reported |
| lnccbrown/HSSM | 206 | 0 | 7 | 23 | SF-09 on an xarray `.values` in a test (likely benign: xarray arrays are writable) |
| AxelNoun/discoursekit | 19 | 0 | 0 | 0 | control |

Raw per-file findings for third-party repositories are not published here: a finding becomes public when it has been reproduced and reported to the maintainers, with the link added to the registry entry.

Known weaknesses, to keep honest: SF-09 cannot tell pandas from xarray (`.values` on a DataArray is writable); SF-19 flags mutable defaults that are never mutated; SF-10 is noisy by design and hidden; SF-01 needs a human to check whether the ids are really the grouping unit. Field precision per detector is tracked in the prospecting pipeline (`PROTOCOL.md`, §5) and detectors under 50 % after 20 reviews are downgraded.

## Why this exists

The author's merged fixes in PyTorch ExecuTorch, PyHealth, Brian2, python-neo, neuroconv, DeepLabCut and HSSM all belong to a small number of recurring classes. Writing them down as a registry makes the audit method reproducible; implementing the detectable ones makes the first look at a codebase take minutes instead of a day. The registry page carries the prose (definitions, prevention, tests to add); this package carries the code.

License: MIT.
