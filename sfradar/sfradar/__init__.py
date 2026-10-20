"""sfradar — Silent Failures Radar.

Static heuristics that flag code patterns known to produce *silent* wrong
results in scientific and ML code: leakage-prone splits, non-injective cache
keys, assertions that cannot fail, exceptions built but never raised, CI steps
that stay green on failure, dtype drops, in-place mutation of pandas-backed
arrays, GPU barriers that do not fence shared memory, and more.

Every detector maps to an entry of the Silent Failures Registry (``registry.py``)
and comes with a real, public specimen (a pull request where the pattern was
found and fixed). The detectors are *screening* tools: they rank where a human
should look first. They are not proofs. Precision and recall are measured on
the fixtures in ``tests/`` and reported in the README.
"""

__version__ = "0.1.0"

from .detectors import DETECTORS, Finding, scan_text  # noqa: F401
from .scan import scan_path  # noqa: F401
