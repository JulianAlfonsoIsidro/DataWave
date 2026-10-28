"""Property-based test for Feature_Assembler schema stability at score time.

# Feature: part1-optin, Property 9: The fitted schema reapplies identically at score time

Covers Property 9 of the part1-optin spec: a ``FeatureSchema`` learned by
:meth:`part1_optin.features.Feature_Assembler.fit_transform` is the authoritative
contract reapplied at score time. Reapplying that frozen schema through
:meth:`part1_optin.features.Feature_Assembler.transform` must produce a matrix
with EXACTLY the schema's columns in the schema's order and identical values to
the fitted matrix -- and, crucially, the score-time column set stays fixed
regardless of *which* leads are scored (Requirements 2.1, 7.2).

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those temp files, the treated-lead population is produced through
:class:`part1_optin.leads.Lead_Loader`, and the Feature_Assembler is then run.
``fit_transform(leads)`` yields ``(X, schema)``. Then:

- ``transform(leads, schema)`` over the full leads must equal ``X`` exactly
  (``pandas.testing.assert_frame_equal``), and its columns must equal
  ``schema.columns`` in order.
- ``transform`` over a SUBSET -- and a *re-ordered* subset -- of the leads must
  still produce columns EXACTLY equal to ``schema.columns`` in order, proving
  score-time column stability regardless of the scored rows.

No path in this test references a ``*_answer_key*`` file; the generated frames
are the only inputs the Feature_Assembler ever reads.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings
from pandas.testing import assert_frame_equal

from part1_optin.config import Config, PROMO_IDS, TREATED_CONTROL_GROUP
from part1_optin.features import Feature_Assembler
from part1_optin.leads import Lead_Loader

from tests.strategies_part1 import consistent_datasets

# Maps each dataset dict key to the Config path field + on-disk filename the
# frame is written to, so a single loop materializes every approved source and
# wires the Config at the temp copies.
_SOURCE_FILES: dict[str, tuple[str, str]] = {
    "leads": ("promo_leads_path", "promo_leads.csv"),
    "customer_dna": ("customer_dna_path", "customer_dna.csv"),
    "product_ownership": ("product_ownership_path", "product_ownership.csv"),
    "adb_monthly": ("adb_monthly_path", "adb_monthly.csv"),
    "contact_history": ("contact_history_path", "contact_history.csv"),
    "ndb": ("ndb_path", "ndb.csv"),
    "part2_features": ("features_part2_path", "features_part2.csv"),
    "promo_history": ("promo_history_path", "promo_history.csv"),
}


def _write_dataset(dataset: dict[str, pd.DataFrame], tmp_dir: Path) -> Config:
    """Write every source frame to a temp CSV and return a Config pointing at them.

    Each approved source frame is written under ``tmp_dir`` with its canonical
    filename, and the matching :class:`Config` path field is overridden to that
    temp copy. The two output paths are left at their defaults -- this test never
    writes an artifact or a scores file. No written path contains ``_answer_key``.
    """
    overrides: dict[str, Path] = {}
    for key, (field_name, filename) in _SOURCE_FILES.items():
        path = tmp_dir / filename
        dataset[key].to_csv(path, index=False)
        overrides[field_name] = path
    return Config(**overrides)


def _has_treated_leads(leads_frame: pd.DataFrame) -> bool:
    """Return whether the raw leads frame yields at least one treated lead.

    Independently re-derives the Lead_Loader's zero-lead guard condition
    (Requirement 1.8) so the test can skip the empty case -- which raises in the
    loader and has no feature matrix to compare -- without reusing loader code.
    A lead survives when it is treated (``control_group == 0``), carries an
    in-set ``promo_id``, and has a ``joined`` value in ``{0, 1}``.
    """
    work = leads_frame.copy()
    work["control_group"] = pd.to_numeric(work["control_group"], errors="coerce")
    work["joined"] = pd.to_numeric(work["joined"], errors="coerce")
    kept = work[
        (work["control_group"] == TREATED_CONTROL_GROUP)
        & (work["promo_id"].isin(PROMO_IDS))
        & (work["joined"].isin([0, 1]))
    ]
    return not kept.empty


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(consistent_datasets())
def test_fitted_schema_reapplies_identically_at_score_time(dataset):
    """The fitted schema reapplies identically at score time.

    **Validates: Requirements 2.1, 7.2**

    ``fit_transform`` yields ``(X, schema)``. ``transform(leads, schema)`` over
    the full leads reproduces ``X`` exactly with columns equal to
    ``schema.columns`` in order. ``transform`` over a subset and a re-ordered
    subset of the leads still produces columns exactly equal to
    ``schema.columns`` -- score-time column stability regardless of scored rows.
    """
    # Skip the zero-treated-leads case: the loader halts there (Requirement 1.8)
    # and there is no feature matrix to compare. Property 9 targets the
    # non-empty assembly.
    if not _has_treated_leads(dataset["leads"]):
        return

    # A self-managed temp dir keeps each Hypothesis example isolated without a
    # function-scoped pytest fixture (which Hypothesis cannot drive per example).
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = _write_dataset(dataset, Path(tmp_dir))

        # The treated-lead population is produced through the real loader so the
        # feature matrix is assembled over exactly the rows the pipeline feeds.
        leads = Lead_Loader(config).load()

        assembler = Feature_Assembler(config)

        # --- Fit the schema and get the trained matrix. ---
        X, schema = assembler.fit_transform(leads)

        # --- Reapply the frozen schema over the FULL leads at "score time". ---
        x_full = assembler.transform(leads, schema)

        # --- Reapply over a SUBSET and a RE-ORDERED subset of the leads. ---
        # A re-ordered subset: take the leads in reverse row order and keep at
        # most the first half, so a non-trivial subset in a non-fit order is
        # scored. With a single treated lead this collapses to that one lead,
        # which still exercises the fixed-column contract.
        reordered = leads.iloc[::-1]
        half = max(1, len(reordered) // 2)
        subset = reordered.iloc[:half]
        x_subset = assembler.transform(subset, schema)

    # --- Full-leads transform: columns EXACTLY equal schema.columns in order. ---
    assert list(x_full.columns) == list(schema.columns)

    # --- Full-leads transform reproduces the fitted matrix exactly, the
    #     score-time stability contract (Requirements 2.1, 7.2). ---
    assert_frame_equal(x_full, X, check_exact=True)

    # --- Subset transform: columns are STILL exactly schema.columns in order,
    #     regardless of which (or how many) rows are scored (Requirement 7.2). ---
    assert list(x_subset.columns) == list(schema.columns)

    # --- The subset matrix has exactly one row per scored lead, confirming the
    #     column stability is a property of the schema, not the row count. ---
    assert len(x_subset) == len(subset)
