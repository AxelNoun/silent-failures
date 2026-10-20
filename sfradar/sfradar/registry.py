"""The Silent Failures Registry, v0.1 — machine-readable half.

Each entry documents one class of defect that produces wrong results without
an error. ``specimen`` points to a public pull request or issue where the
pattern was found and fixed; the numbers quoted there are the ones reported in
that thread. ``refs`` cite the literature that names or studies the class.

The prose half (definitions, prevention, tests to add) lives in the Registry
page; both halves share the identifiers below.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Entry:
    id: str
    name_en: str
    name_fr: str
    family: str  # data | numerics | concurrency | control-flow | build-ci | codegen
    detectable: str  # "static" | "heuristic" | "manual"
    specimen: str
    specimen_note: str
    refs: tuple[str, ...] = field(default_factory=tuple)


REFS = {
    "kapoor2023": "Kapoor, S. & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. Patterns 4(9), 100804.",
    "kaufman2012": "Kaufman, S., Rosset, S., Perlich, C. & Stitelman, O. (2012). Leakage in data mining: formulation, detection, and avoidance. ACM TKDD 6(4).",
    "lones2021": "Lones, M. A. (2021). How to avoid machine learning pitfalls: a guide for academic researchers. arXiv:2108.02497.",
    "pineau2021": "Pineau, J. et al. (2021). Improving reproducibility in machine learning research: a report from the NeurIPS 2019 reproducibility program. JMLR 22(164).",
    "roberts2021": "Roberts, M. et al. (2021). Common pitfalls and recommendations for using machine learning to detect and prognosticate for COVID-19 using chest radiographs and CT scans. Nature Machine Intelligence 3, 199–217.",
    "goldberg1991": "Goldberg, D. (1991). What every computer scientist should know about floating-point arithmetic. ACM Computing Surveys 23(1).",
    "lipp2023": "Metal Shading Language Specification, §6.9 Synchronization and SIMD-group functions (threadgroup_barrier, mem_flags). Apple.",
}

ENTRIES: list[Entry] = [
    Entry("SF-01", "Grouped-entity leakage across splits", "Fuite d'entité groupée entre splits", "data", "heuristic",
          "https://github.com/sunlabuiuc/PyHealth/pull/1187",
          "PTB-XL: a patient can have several records; a random split puts the same patient on both sides. The PR adds a patient-disjoint check to split_by_strat_fold.",
          ("kapoor2023", "kaufman2012", "roberts2021")),
    Entry("SF-02", "Target information inside the features", "Information de la cible dans les variables", "data", "manual",
          "https://github.com/sunlabuiuc/PyHealth/pull/1203",
          "OMOP drug recommendation: the current visit's drugs were in the history fed to the model, so the last history entry equalled the prediction target.",
          ("kaufman2012", "kapoor2023")),
    Entry("SF-03", "Negatives sampled from the evaluation set", "Négatifs tirés du jeu d'évaluation", "data", "manual",
          "https://github.com/sunlabuiuc/PyHealth/pull/1202",
          "Knowledge-graph embeddings: training negatives must be drawn from training triples only; drawing from all triples leaks evaluation structure into training.",
          ("kapoor2023",)),
    Entry("SF-04", "Non-injective or unstable cache key", "Clé de cache non injective ou instable", "data", "static",
          "https://github.com/sunlabuiuc/PyHealth/pull/1207",
          "set_task derived its cache key from json.dumps(vars(task), default=str): str() truncates arrays past 1000 elements and embeds memory addresses, so two configurations could share a cache and one could fail to reuse its own.",
          ("pineau2021",)),
    Entry("SF-05", "Assertion that cannot fail", "Assertion qui ne peut pas échouer", "control-flow", "static",
          "https://github.com/pytorch/executorch/pull/22373",
          "assert f\"Unsupported ... {axis}\": the f-string is always truthy, so the guard never fires, and vanishes under python -O.",
          ()),
    Entry("SF-06", "Exception constructed but never raised", "Exception construite mais jamais levée", "control-flow", "static",
          "https://github.com/pytorch/executorch/pull/22373",
          "RuntimeError(\"Weight of 1d conv should be constant\") built as a bare expression; execution continues with the wrong shape.",
          ()),
    Entry("SF-07", "CI step that stays green on failure", "Étape de CI verte sur échec", "build-ci", "static",
          "https://github.com/NeuralEnsemble/python-neo/pull/1912",
          "echo \"hash=$(git ls-remote ... | cut -f1)\" >> $GITHUB_OUTPUT: the step's exit status is echo's; on HTTP 403 the hash is empty and the cache key degrades silently. 9 + 12 runs counted in the logs.",
          ()),
    Entry("SF-08", "dtype dropped when lifting a scalar", "dtype perdu en promouvant un scalaire", "numerics", "static",
          "https://github.com/pytorch/executorch/pull/22372",
          "torch.tensor(float(args[i])) turned every lifted integer into float32; an int64 add used as an index then failed, and a bare VulkanQuantizer() hit it unconditionally.",
          ("goldberg1991",)),
    Entry("SF-09", "In-place mutation of a view that may be read-only", "Mutation en place d'une vue potentiellement en lecture seule", "data", "static",
          "https://github.com/DeepLabCut/DeepLabCut/pull/3445",
          "pandas 3 Copy-on-Write returns read-only arrays from .values / .to_numpy(); ten in-place writes across eight modules either raise or silently stop updating the frame.",
          ()),
    Entry("SF-10", "Unseeded randomness on the evaluation path", "Aléa non graine sur le chemin d'évaluation", "data", "heuristic",
          "https://github.com/AxelNoun/kinoscope",
          "kinoscope seeds every generator and tests bit-for-bit determinism; the absence of seeding makes a metric irreproducible and hides regressions in noise.",
          ("pineau2021", "lones2021")),
    Entry("SF-11", "Parameter order coupled across libraries", "Ordre de paramètres couplé entre bibliothèques", "data", "manual",
          "https://github.com/lnccbrown/HSSM/pull/1371",
          "HSSM listed (A, b, v0, v1, v2, t); the simulator registry expected (v0, v1, v2, A, b, t). Fits were fine; predictive draws had mean RT 0.88 s instead of 0.337 s.",
          ()),
    Entry("SF-12", "Shared-memory exchange without a fencing barrier", "Échange en mémoire partagée sans barrière", "concurrency", "static",
          "https://github.com/ml-explore/mlx-lm/pull/1719",
          "Fused Metal KL/JS kernels reused one threadgroup buffer for the max and the sum exchanges with threadgroup_barrier(mem_flags::mem_none) between them: 50/50 nondeterministic runs before, 0/50 after.",
          ("lipp2023",)),
    Entry("SF-13", "Fast-math transcendental on an unbounded argument", "Fonction fast-math sur un argument non borné", "numerics", "heuristic",
          "https://github.com/ml-explore/mlx-lm/pull/1719",
          "log(1 + exp(d)) overflowed deterministically at logit scale 20 in the JS kernels; replaced by a stable softplus.",
          ("goldberg1991",)),
    Entry("SF-14", "Wrong symbol substituted in generated code", "Mauvais symbole substitué dans du code généré", "codegen", "manual",
          "https://github.com/brian-team/brian2/pull/1891",
          "The Cython Binomial template used p where the inversion algorithm needs P = min(p, 1-p): mean 9.11 instead of 8 for n=10, p=0.8, for years.",
          ()),
    Entry("SF-15", "Constant rounded by its printed precision", "Constante arrondie par sa précision d'impression", "codegen", "heuristic",
          "https://github.com/brian-team/brian2/pull/1891",
          "Constants written with 15 decimals rounded (1-P)**n to zero in the generated loop, which then never terminated. repr(float(x)) is exact.",
          ("goldberg1991",)),
    Entry("SF-16", "Dangling pointer into a refilled buffer", "Pointeur pendant vers un tampon rempli à nouveau", "concurrency", "manual",
          "https://github.com/brian-team/brian2/issues/1893",
          "get_random_state copied a raw pointer to a 20,000-number buffer; after a refill, restore() read freed memory (wrong values or double free).",
          ()),
    Entry("SF-17", "Narrow integer offset in a vectorized kernel", "Offset entier étroit dans un kernel vectorisé", "numerics", "manual",
          "https://github.com/pytorch/pytorch/issues/200949",
          "grid_sample on CPU computes gather offsets in int16 for fp16/bf16 inputs; past 32,767 the offset wraps and the output is wrong or NaN. Labelled 'module: correctness (silent)'.",
          ()),
    Entry("SF-18", "Exception swallowed", "Exception avalée", "control-flow", "static",
          "https://github.com/sunlabuiuc/PyHealth/pull/1174",
          "Bare except / except: pass hides the failure that would have told you the result is wrong.",
          ("lones2021",)),
    Entry("SF-19", "Aliased mutable state across samples", "État mutable partagé entre échantillons", "data", "static",
          "https://github.com/sunlabuiuc/PyHealth/pull/1203",
          "Nested history lists were shared between samples, so mutating one sample mutated the others; fixed by copying.",
          ()),
    Entry("SF-20", "Test that cannot detect its own regression", "Test incapable de détecter sa régression", "control-flow", "manual",
          "https://github.com/sunlabuiuc/PyHealth/pull/1203",
          "The leakage test mocked exactly the path it should have exercised; re-introducing the leak kept it green. Method: inject the regression and watch the test.",
          ("pineau2021",)),
]

BY_ID = {e.id: e for e in ENTRIES}
