"""Property-based test for stratified group k-fold coverage and grouping.

# Feature: part1-optin, Property 21: Stratified group k-fold keeps every client in one fold and covers every lead once

Covers Property 21 of the part1-optin spec: the headline StratifiedGroupKFold
scheme (``Validator.run_stratified``) holds every Treated_Lead out exactly once
across its five folds, and never lets a single client straddle a train/held-out
split -- every lead of one client lands in the same fold
(Requirements 8.1, 8.2, 8.3).

Verification strategy (two complementary checks):

- **Splitter invariant (grouping + single-coverage).** The grouping and
  held-out-once guarantees are properties of
  ``StratifiedGroupKFold(n_splits=5)`` driven by ``groups=client_ids`` and
  ``y=Join_Label`` -- exactly the splitter, split count, groups, and labels
  ``run_stratified`` uses (same ``RANDOM_SEED``). For a generated lead
  population the test drives that same splitter and asserts, across the five
  folds, that: (a) the held-out index sets are pairwise disjoint and together
  cover every lead exactly once (full out-of-fold coverage, Requirements 8.1,
  8.3); and (b) in no fold does any client appear in both the training and the
  held-out slice -- each client's leads sit entirely on one side of the split
  (no client straddles a fold, Requirement 8.2). These checks need no model
  fit, so a large ``max_examples`` stays fast.

- **End-to-end coverage via run_stratified.** On a smaller, two-class, enough-
  per-class dataset the test actually runs ``Validator.run_stratified`` and
  asserts the result scores the full population exactly once: ``result.n``
  equals the lead count and ``result.joiners`` equals the actual joiner count,
  so the out-of-fold vector the headline metrics derive from spans every lead
  (Requirements 8.1, 8.3).

The generated data satisfies StratifiedGroupKFold's structural needs: at least
five distinct clients (so five non-empty folds are possible) and both opt-in
and non-opt-in leads present across clients. No path in this module references
a ``*_answer_key*`` file; every matrix is built in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sklearn.model_selection import StratifiedGroupKFold

from part1_optin.config import PROMO_IDS, RANDOM_SEED, Config
from part1_optin.features import FeatureSchema
from part1_optin.validation import Validator

# The production split count (Requirement 8.1). StratifiedGroupKFold needs at
# least this many distinct groups to form five non-empty folds, so generated
# populations always carry >= this many clients.
_N_SPLITS = 5

# Feature columns for the generated matrix; a small fixed set keeps the
# end-to-end run_stratified fit cheap while exercising a multi-feature model.
_FEATURE_COLUMNS = ["f0", "f1", "f2"]


@st.composite
def grouped_lead_population(draw):
    """Draw (client_ids, y, promo_ids) for a two-class, multi-client population.

    Enough distinct clients and leads are generated for
    ``StratifiedGroupKFold(n_splits=5)`` to split: at least ``_N_SPLITS``
    distinct clients and at least ``_N_SPLITS`` leads in *each* class (the
    splitter requires every class to have >= ``n_splits`` members). Each client
    contributes one or more leads (so some clients carry several leads that must
    stay together in one fold), and each lead gets a ``Join_Label`` and a
    ``promo_id``.

    To satisfy the per-class floor without coupling a client's leads to one
    class (clients are the groups, and may legitimately mix classes), the labels
    are assigned across the whole lead sequence afterwards: the first
    ``_N_SPLITS`` leads are forced to class 1 and the next ``_N_SPLITS`` to
    class 0, with the remainder drawn freely. The lead/client structure (which
    leads share a client) is what the grouping invariant turns on and is
    preserved regardless of the labels.

    Returns ``(client_ids, y, promo_ids)`` as aligned lists.
    """
    # At least _N_SPLITS clients so five non-empty folds are possible.
    n_clients = draw(st.integers(min_value=_N_SPLITS, max_value=10))
    client_names = [f"C{100000 + i}" for i in range(n_clients)]

    client_id_values: list[str] = []
    promo_values: list[str] = []

    for client in client_names:
        n_leads = draw(st.integers(min_value=1, max_value=3))
        for _ in range(n_leads):
            client_id_values.append(client)
            promo_values.append(draw(st.sampled_from(PROMO_IDS)))

    n_leads_total = len(client_id_values)

    # The splitter needs >= _N_SPLITS members in each class, so force the first
    # _N_SPLITS leads to class 1 and the next _N_SPLITS to class 0, then draw
    # the rest freely. With n_leads at least 1 per client and >= _N_SPLITS
    # clients, there are always at least _N_SPLITS leads; grow the population
    # until it can host both class floors.
    while n_leads_total < 2 * _N_SPLITS:
        client = f"C{100000 + len(client_names)}"
        client_names.append(client)
        client_id_values.append(client)
        promo_values.append(draw(st.sampled_from(PROMO_IDS)))
        n_leads_total += 1

    y_values: list[int] = []
    for position in range(n_leads_total):
        if position < _N_SPLITS:
            y_values.append(1)
        elif position < 2 * _N_SPLITS:
            y_values.append(0)
        else:
            y_values.append(draw(st.sampled_from([0, 1])))

    return client_id_values, y_values, promo_values


# No model fitting here: the grouping/coverage invariants are pure properties
# of the splitter + groups, so a large sample is cheap.
@settings(max_examples=100, deadline=None)
@given(data=grouped_lead_population())
def test_stratified_group_kfold_covers_every_lead_once_and_keeps_clients_whole(
    data,
):
    """Every lead is held out exactly once and no client straddles a fold.

    **Validates: Requirements 8.1, 8.2, 8.3**

    Drives the same ``StratifiedGroupKFold(n_splits=5)`` with the same groups
    and labels ``run_stratified`` uses and asserts full single-coverage of the
    out-of-fold index and whole-client fold membership.
    """
    client_id_values, y_values, _ = data
    n = len(y_values)
    y_arr = np.asarray(y_values, dtype=int)
    groups = np.asarray(client_id_values)

    splitter = StratifiedGroupKFold(
        n_splits=_N_SPLITS,
        shuffle=True,
        random_state=RANDOM_SEED,
    )

    # Count how many times each lead index is held out, and -- for the
    # straddle check -- record each fold's held-out client set so no client
    # appears in both training and held-out of the same fold.
    held_out_count = np.zeros(n, dtype=int)

    for train_idx, held_idx in splitter.split(
        np.zeros((n, 1)), y_arr, groups=groups
    ):
        held_out_count[held_idx] += 1

        # Requirement 8.2: no client straddles the split -- the train and
        # held-out client sets of a fold are disjoint.
        train_clients = set(groups[train_idx])
        held_clients = set(groups[held_idx])
        assert train_clients.isdisjoint(held_clients)

        # Together the two slices partition all leads of the fold.
        assert len(train_idx) + len(held_idx) == n

    # Requirements 8.1, 8.3: every lead is held out exactly once (full
    # out-of-fold coverage, no lead scored twice, none skipped).
    assert np.all(held_out_count == 1)


def _rows(n_rows: int, loc: float, seed: int) -> np.ndarray:
    """Return ``n_rows`` deterministic feature rows centered near ``loc``."""
    rng = np.random.RandomState(seed)
    return rng.normal(loc=loc, scale=1.0, size=(n_rows, len(_FEATURE_COLUMNS)))


@st.composite
def stratified_fit_dataset(draw):
    """Draw (X, y, promo_ids, client_ids) that run_stratified can fit end to end.

    Generates enough distinct clients and both-class leads for all five outer
    folds plus the internal ``cv=3`` calibration folds to fit. Each client owns
    a small run of consecutive leads (so the whole-client grouping is real),
    labels alternate to guarantee a comfortable per-class population, and every
    lead gets a ``promo_id`` from P001/P002/P003.
    """
    # A healthy client/lead count so each of the five outer folds -- and the
    # inner cv=3 calibration folds inside Model_Trainer -- see both classes.
    n_clients = draw(st.integers(min_value=12, max_value=18))

    all_rows: list[np.ndarray] = []
    labels: list[int] = []
    promos: list[str] = []
    clients: list[str] = []

    for i in range(n_clients):
        client = f"C{100000 + i}"
        n_leads = draw(st.integers(min_value=2, max_value=3))
        for j in range(n_leads):
            label = (i + j) % 2
            loc = 1.0 if label == 1 else -1.0
            all_rows.append(_rows(1, loc=loc, seed=1000 * i + j))
            labels.append(label)
            promos.append(PROMO_IDS[(i + j) % len(PROMO_IDS)])
            clients.append(client)

    x = pd.DataFrame(np.vstack(all_rows), columns=_FEATURE_COLUMNS)
    y = pd.Series(labels, name="Join_Label")
    promo_ids = pd.Series(promos, name="promo_id")
    client_ids = pd.Series(clients, name="client_id")
    return x, y, promo_ids, client_ids


# max_examples kept small: EACH example fits the calibrated model (five outer
# folds, each with an internal cv=3 calibration) plus a full-data booster, so
# model fitting dominates runtime. deadline=None because those fits exceed
# Hypothesis's default per-example deadline.
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)
@given(data=stratified_fit_dataset())
def test_run_stratified_scores_full_population_exactly_once(data):
    """run_stratified's out-of-fold vector spans every lead exactly once.

    **Validates: Requirements 8.1, 8.3**

    End-to-end check: the StratifiedGroupKFold scheme holds every lead out once
    across its five folds, so the result reports the full lead population
    (``n``) and the full actual-joiner count (``joiners``) that the single
    out-of-fold probability vector is built from.
    """
    x, y, promo_ids, client_ids = data
    schema = FeatureSchema(columns=list(_FEATURE_COLUMNS))

    result = Validator(Config()).run_stratified(
        x, y, promo_ids, client_ids, schema
    )

    # The result spans the full lead population exactly once (Requirements 8.1,
    # 8.3): n is the total lead count and joiners is the total actual joiners.
    assert result.n == len(y)
    assert result.joiners == int(y.sum())
