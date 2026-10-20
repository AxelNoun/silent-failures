"""Detectors for the statically or heuristically detectable Registry entries.

A detector takes a file's text (and path) and yields ``Finding`` objects. Two
kinds exist: AST detectors (Python only, exact on structure) and regex
detectors (any text: YAML workflows, Metal/CUDA sources, templates).

Confidence is a coarse, honest label:
  - "high":   the pattern itself is the defect (an assert on a literal, an
              exception built and dropped, a step whose exit status is echo's).
  - "medium": the pattern is a defect in most contexts (json.dumps default=str
              near a cache/hash, .values[...] = ..., torch.tensor(float(x))).
  - "low":    the pattern is a *risk* that needs a human to confirm (random
              split next to an id column, unseeded RNG, fast::exp unguarded).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, asdict
from typing import Callable, Iterable, Iterator

EXC_NAMES = {
    "Exception", "RuntimeError", "ValueError", "TypeError", "KeyError", "IndexError", "AssertionError",
    "NotImplementedError", "AttributeError", "OSError", "IOError", "LookupError", "ArithmeticError",
}


@dataclass
class Finding:
    id: str            # registry id, e.g. "SF-05"
    path: str
    line: int
    confidence: str    # high | medium | low
    snippet: str
    rationale: str
    test_hint: str

    def to_dict(self) -> dict:
        return asdict(self)


Detector = Callable[[str, str], Iterator[Finding]]


def _line(text: str, lineno: int) -> str:
    lines = text.splitlines()
    return lines[lineno - 1].strip()[:200] if 0 < lineno <= len(lines) else ""


# --------------------------------------------------------------------------- AST
def _parse(text: str):
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def det_assert_cannot_fail(path: str, text: str) -> Iterator[Finding]:
    """SF-05: assert on a non-empty string literal / f-string / tuple is always true."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            t = node.test
            always = (
                isinstance(t, ast.JoinedStr)
                or (isinstance(t, ast.Constant) and isinstance(t.value, str) and t.value != "")
                or (isinstance(t, ast.Tuple) and len(t.elts) > 0)
            )
            if always:
                yield Finding("SF-05", path, node.lineno, "high", _line(text, node.lineno),
                              "The asserted expression is a non-empty literal (or a tuple), so it is always truthy: the guard can never fire, and the whole statement disappears under python -O.",
                              "Replace with an explicit `if not cond: raise ...` and add a test that enters the branch.")


def det_exception_not_raised(path: str, text: str) -> Iterator[Finding]:
    """SF-06: a bare expression statement that constructs an exception."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            camel_exc = re.fullmatch(r"[A-Z][A-Za-z]*(?:Error|Exception|Warning)", name) is not None
            # an Attribute call like obj.PL2_GetLastError(...) is a method, not an exception class
            if name in EXC_NAMES or (camel_exc and isinstance(fn, ast.Name)):
                yield Finding("SF-06", path, node.lineno, "high", _line(text, node.lineno),
                              f"{name}(...) is constructed and immediately discarded: nothing is raised and execution continues past the documented failure.",
                              "Prefix with `raise`; add a test that reaches this path and expects the exception.")


def det_mutable_default(path: str, text: str) -> Iterator[Finding]:
    """SF-19 (weak form): mutable default argument shared across calls."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    yield Finding("SF-19", path, d.lineno, "medium", _line(text, d.lineno),
                                  "A mutable default is created once and shared by every call; appending to it leaks state between calls (and between samples in a dataset pipeline).",
                                  "Use None and build the container inside; add a test calling twice and asserting independence.")


def det_exception_swallowed(path: str, text: str) -> Iterator[Finding]:
    """SF-18: bare except or except Exception whose body only passes/continues."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"})
            trivial = all(isinstance(s, (ast.Pass, ast.Continue)) for s in node.body)
            if broad and trivial:
                yield Finding("SF-18", path, node.lineno, "medium", _line(text, node.lineno),
                              "A broad handler that only passes hides the failure that would have told you the result is wrong.",
                              "Narrow the exception type and log or re-raise; add a test that the failure is surfaced.")


def _key(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _key(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _base_of(node):
    """Strip subscripts/attribute-calls (.reshape, .T, .swapaxes, slices) down to the underlying name."""
    while True:
        if isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {
                "reshape", "swapaxes", "transpose", "squeeze", "ravel", "view", "astype"}:
            node = node.func.value
        elif isinstance(node, ast.Attribute) and node.attr in {"T", "flat"}:
            node = node.value
        else:
            return node


def _derives_from_frame_view(node) -> bool:
    """True when the expression contains .values or .to_numpy() without copy=True."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "values" and not isinstance(getattr(sub, "ctx", None), ast.Store):
            # exclude dict.values() calls: those appear as Call(func=Attribute values)
            return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "to_numpy":
            if not any(k.arg == "copy" and isinstance(k.value, ast.Constant) and k.value.value is True for k in sub.keywords):
                return True
    return False


def _is_dict_values_call(node) -> bool:
    return any(isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "values" and not sub.args
               for sub in ast.walk(node))


def det_frame_view_mutated(path: str, text: str) -> Iterator[Finding]:
    """SF-09 (taint form): an array taken from .values/.to_numpy() is later written in place."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    tainted: dict[str, int] = {}
    stores: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            val = node.value
            if _derives_from_frame_view(val) and not _is_dict_values_call(val):
                for t in node.targets:
                    k = _key(t)
                    if k:
                        tainted.setdefault(k, node.lineno)
            else:
                b = _key(_base_of(val))
                if b in tainted:
                    for t in node.targets:
                        k = _key(t)
                        if k:
                            tainted.setdefault(k, tainted[b])
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript):
                    k = _key(_base_of(t))
                    if k:
                        stores.append((k, node.lineno))
    seen = set()
    for k, lineno in stores:
        if k in tainted and (k, lineno) not in seen:
            seen.add((k, lineno))
            yield Finding("SF-09", path, lineno, "medium", _line(text, lineno),
                          f"`{k}` is a view obtained from a DataFrame (.values / .to_numpy() without copy=True, line {tainted[k]}) and is written in place here; under pandas 3 Copy-on-Write that array is read-only, so the write raises or silently stops reaching the frame.",
                          "Materialise with .to_numpy(copy=True) when the array is mutated, or write through .loc; run the tests under pandas>=3.")


# ------------------------------------------------------------------------- REGEX
def _regex_detector(regex: str, sid: str, confidence: str, rationale: str, test_hint: str,
                    exts: tuple[str, ...] = (), flags=re.M) -> Detector:
    pat = re.compile(regex, flags)

    def det(path: str, text: str) -> Iterator[Finding]:
        if exts and not path.endswith(exts):
            return
        for m in pat.finditer(text):
            lineno = text.count("\n", 0, m.start()) + 1
            yield Finding(sid, path, lineno, confidence, _line(text, lineno), rationale, test_hint)
    return det


def det_cache_key_default_str(path: str, text: str) -> Iterator[Finding]:
    """SF-04: json.dumps(..., default=str) (multi-line aware, AST based)."""
    if not path.endswith(".py"):
        return
    tree = _parse(text)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dumps":
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Name) and kw.value.id in {"str", "repr"}:
                    yield Finding("SF-04", path, node.lineno, "medium", _line(text, node.lineno),
                                  "json.dumps(..., default=str) stringifies anything non-serialisable: str() truncates large arrays, embeds memory addresses and depends on hash seeds, so the result is neither injective nor stable across processes. Fatal when used as a cache or fingerprint key.",
                                  "Build keys from an explicit canonicaliser that raises on unknown types; test that two different configs give different keys and the same config the same key across processes.")

det_dtype_dropped = _regex_detector(
    r"torch\.tensor\(\s*(?:float|int)\(", "SF-08", "medium",
    "torch.tensor(float(x)) fixes the dtype to the default float regardless of the node's recorded dtype; integer scalars used as indices or masks then fail or change meaning.",
    "Pass dtype=<source dtype> explicitly; add a test with an int64 scalar.",
    exts=(".py",))

det_values_inplace = _regex_detector(
    r"\.(?:values|to_numpy\(\))\s*\[[^\]\n]*\]\s*(?:=|\+=|-=|\*=|/=)(?!=)", "SF-09", "medium",
    "Writing into .values / .to_numpy() mutates a view that pandas 3 (Copy-on-Write) hands out read-only: the write raises, or silently stops reaching the DataFrame.",
    "Assign through .loc / .iloc, or call .to_numpy(copy=True) when a scratch array is intended; test under pandas>=3.",
    exts=(".py",))

det_ci_green_on_failure = _regex_detector(
    r"^[ \t]*(?:-[ \t]*)?(?:run:[ \t]*\|?[ \t]*)?echo[ \t]+\"?[A-Za-z_][\w-]*=\$\((?!.*set -o pipefail).*\)\"?[ \t]*>>[ \t]*\"?\$\{?GITHUB_(?:OUTPUT|ENV)", "SF-07", "high",
    "echo \"name=$(cmd)\" >> $GITHUB_OUTPUT reports echo's exit status, not cmd's: when cmd fails the step stays green and the output is empty.",
    "Add `set -euo pipefail`, assign first, test non-emptiness, emit ::error:: and exit 1; test by pointing cmd at an unreachable host.",
    exts=(".yml", ".yaml"))

det_continue_on_error = _regex_detector(
    r"^[ \t]*continue-on-error:[ \t]*true", "SF-07", "low",
    "continue-on-error: true turns a failing step green at the job level; acceptable for optional diagnostics, dangerous on a test or build step.",
    "Confirm the step is optional; otherwise remove and fix the failure.",
    exts=(".yml", ".yaml"))

det_or_true = _regex_detector(
    r"\|\|\s*true\b", "SF-07", "low",
    "`|| true` masks the exit status of the preceding command.",
    "Remove or restrict to commands whose failure is genuinely irrelevant.",
    exts=(".yml", ".yaml", ".sh", "Makefile"))

det_barrier_mem_none = _regex_detector(
    r"threadgroup_barrier\(\s*mem_flags::mem_none\s*\)", "SF-12", "medium",
    "threadgroup_barrier(mem_flags::mem_none) synchronises execution but does not fence threadgroup memory; if shared storage is written before and read after, the read may see stale data.",
    "Use mem_flags::mem_threadgroup when shared memory is exchanged; add a many-run determinism test (N identical launches, assert bitwise equality).",
    exts=(".metal", ".h", ".py", ".cpp", ".mm"))

det_fast_exp_unguarded = _regex_detector(
    r"metal::fast::(?:exp|log)\(", "SF-13", "low",
    "metal::fast:: transcendental functions have no range guarantees; an unbounded argument (a log-sum-exp difference, log(1+exp(x))) can overflow or return garbage for large magnitudes.",
    "Clamp or rewrite as a stable form (softplus, max-subtraction); test at logit scale 20+ against float64.",
    exts=(".metal", ".py", ".h", ".cpp"))

det_random_split_near_ids = _regex_detector(
    r"train_test_split\((?![^)]*(?:stratify|groups))[^)]*\)|(?<![A-Za-z])KFold\((?![^)]*groups)[^)]*shuffle\s*=\s*True", "SF-01", "low",
    "A random split in a file that also mentions grouping identifiers (patient, subject, session, visit, user, record) risks placing the same entity on both sides.",
    "Use GroupKFold / GroupShuffleSplit keyed on the entity id; add a test asserting the id sets are disjoint across splits.",
    exts=(".py",))

det_unseeded_random = _regex_detector(
    r"\b(?:np\.random\.(?:rand|randn|randint|choice|permutation|shuffle)|random\.(?:random|randint|choice|shuffle|sample)|torch\.(?:rand|randn|randint|randperm))\(", "SF-10", "low",
    "Global-state randomness on an evaluation or split path without a visible seed makes the metric irreproducible; regressions hide in the noise.",
    "Pass an explicit Generator / seed; test bit-for-bit equality of two runs.",
    exts=(".py",))

det_printed_precision_constants = _regex_detector(
    r"(?:%\.1[0-7][fge]|:\.1[0-7][fg]\})", "SF-15", "low",
    "A float formatted with a fixed decimal count in generated code loses bits; repr(float(x)) is the shortest exact representation.",
    "Emit constants with repr(); test the generated constant round-trips to the original float.",
    exts=(".py", ".pyx", ".jinja", ".template", ".tmpl"))


_ID_WORDS = re.compile(r"\b(?:patient|subject|session|visit|user|record|study|animal|participant)_?(?:id|ids)?\b", re.I)


def det_sf01_with_context(path: str, text: str) -> Iterator[Finding]:
    """SF-01 only fires when grouping identifiers appear in the same file (reduces false positives)."""
    if not _ID_WORDS.search(text):
        return
    yield from det_random_split_near_ids(path, text)


def det_sf10_with_context(path: str, text: str) -> Iterator[Finding]:
    """SF-10 only fires when no seeding call is visible anywhere in the file."""
    if re.search(r"(?:seed\(|manual_seed\(|default_rng\(|Generator\(|RandomState\()", text):
        return
    yield from det_unseeded_random(path, text)


DETECTORS: dict[str, Detector] = {
    "SF-01": det_sf01_with_context,
    "SF-04": det_cache_key_default_str,
    "SF-05": det_assert_cannot_fail,
    "SF-06": det_exception_not_raised,
    "SF-07a": det_ci_green_on_failure,
    "SF-07b": det_continue_on_error,
    "SF-07c": det_or_true,
    "SF-08": det_dtype_dropped,
    "SF-09a": det_values_inplace,
    "SF-09b": det_frame_view_mutated,
    "SF-10": det_sf10_with_context,
    "SF-12": det_barrier_mem_none,
    "SF-13": det_fast_exp_unguarded,
    "SF-15": det_printed_precision_constants,
    "SF-18": det_exception_swallowed,
    "SF-19": det_mutable_default,
}


def scan_text(path: str, text: str, only: Iterable[str] | None = None) -> list[Finding]:
    """Run every (or the selected) detectors on one file's text."""
    out: list[Finding] = []
    for key, det in DETECTORS.items():
        if only and key.rstrip("abc") not in only and key not in only:
            continue
        out.extend(det(path, text))
    return out
