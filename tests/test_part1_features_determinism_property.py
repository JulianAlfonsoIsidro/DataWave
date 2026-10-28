"""Property-based test for Feature_Assembler determinism and stable encoding.

# Feature: part1-optin, Property 2: Feature assembly is deterministic with stable categorical encoding

Covers Property 2 of the part1-optin spec: given any internally consistent set
of approved source frames, :meth:`part1_optin.features.Feature_Assembler.fit_transform`
produces a byte-identical feature matrix and categorical encoding on repeated
runs over identical inputs, and the frozen schema reapplied through
:meth:`part1_optin.features.Feature_Assembler.transform` reproduces that same
matrix (Requirement 2.1).

The test exercises the real file-reading path: every generated source frame is
written to a temporary CSV, a :class:`part1_optin.config.Config` is pointed at
those temp files, the treated-lead population is produced through
:class:`part1_optin.leads.Lead_Loader`, and the Feature_Assembler is then run
twice on those treated leads. The two fitted matrices must be identical in
column set, column order, and every value, and the two fitted ``FeatureSchema``
categorical maps (and the rest of the schema) must be identical. Finally a
``transform(leads, schema)`` call using the first fit's frozen schema must
reproduce the first fit's matrix exactly -- the score-time stability contract
(Requirements 2.1, 7.2).

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
def test_feature_assembly_is_deterministic_with_stable_encoding(dataset):
    """Feature assembly is deterministic with stable categorical encoding.

    **Validates: Requirements 2.1**

    Two ``fit_transform`` runs over identical inputs yield identical matrices
    (same columns, same order, same values) and identical categorical maps, and
    a ``transform`` through the first fit's frozen schema reproduces the first
    matrix.
    """
    # Skip the zero-treated-leads case: the loader halts there (Requirement 1.8)
    # and there is no feature matrix to compare. Property 2 targets the
    # non-empty assembly.
    if not _has_treated_leads(dataset["leads"]):
        return

    # A self-managed temp dir keeps each Hypothesis example isolated without a
    # function-scoped pytest fixture (which Hypothesis cannot drive per example).
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = _write_dataset(dataset, Path(tmp_dir))

        # The treated-lead population is produced through the real loader so the
        # feature matrix is assembled over exactly the rows the pipeline would
        # feed it.
        leads = Lead_Loader(config).load()

        assembler = Feature_Assembler(config)

        # --- Run fit_transform TWICE on the same treated leads. ---
        x1, schema1 = assembler.fit_transform(leads)
        x2, schema2 = assembler.fit_transform(leads)

        # --- Re-apply the first fit's frozen schema at "score time". ---
        x_transform = assembler.transform(leads, schema1)

    # --- Same column set and order across both fits. ---
    assert list(x1.columns) == list(x2.columns)

    # --- Identical matrices: same columns, order, and every value. ---
    assert_frame_equal(x1, x2, check_exact=True)

    # --- Identical categorical encoding maps (the stable-encoding core). ---
    assert schema1.categorical_maps == schema2.categorical_maps

    # --- The rest of the schema is identical too (column order, discovered
    #     product-type and part2 columns). ---
    assert schema1.columns == schema2.columns
    assert schema1.product_type_columns == schema2.product_type_columns
    assert schema1.part2_columns == schema2.part2_columns

    # --- transform through the frozen schema reproduces the fitted matrix
    #     exactly, the score-time stability contract (Requirements 2.1, 7.2). ---
    assert list(x_transform.columns) == list(x1.columns)
    assert_frame_equal(x_transform, x1, check_exact=True)
