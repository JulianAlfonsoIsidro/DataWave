"""Example/edge unit tests for the Part1_Optin Scorer and score_promo (task 10.6).

Targeted (non-Hypothesis) tests for the batch :class:`part1_optin.scoring.Scorer`
and the module-level :func:`part1_optin.scoring.score_promo`, covering:

- The written ``scores.csv`` header is exactly the six fixed columns in order
  with no index column (Requirement 6.3).
- :func:`score_promo` accepts a ``promo_dict`` carrying ``promo_id`` /
  ``mechanic`` / ``threshold_php`` and a ``clients_df``, and returns one row per
  client whose feature matrix matched the trained schema, applying the existing
  model without retraining and attaching three top SHAP drivers
  (Requirements 7.1, 7.2, 7.3, 7.5).
- :func:`score_promo` with an unseen mechanic emits a warning and still returns
  a valid ``p_join`` in ``[0, 1]`` for every client (Requirement 7.4).

Each test builds a realistic fitted model the only way ``score_promo`` can work:
it writes small valid CSVs for all eight approved sources to pytest's
``tmp_path``, points a :class:`~part1_optin.config.Config` at them, loads the
treated leads through :class:`~part1_optin.leads.Lead_Loader`, assembles the
feature matrix and schema through :meth:`Feature_Assembler.fit_transform`, and
fits :class:`~part1_optin.model.Model_Trainer`. ``score_promo`` then calls
``Feature_Assembler.transform`` which re-reads those same source files from the
Config, so the transform reproduces the trained column set/order/encoding.

The treated-lead population spans P001/P002/P003 with at least three joiners and
three non-joiners, so the internal ``cv=3`` ``StratifiedKFold`` of
``CalibratedClassifierCV`` sees both classes in every fold. No fixture or path
references a ``*_answer_key*`` file (Requirement 2.14).
"""

from __future__ import annotations

import csv
import warnings
from pathlib import Path

import pandas as pd

from part1_optin.config import Config
from part1_optin.features import Feature_Assembler
from part1_optin.leads import Lead_Loader
from part1_optin.model import Calibrated_Model, Model_Trainer
from part1_optin.scoring import (
    SCORE_COLUMNS,
    SCORE_PROMO_COLUMNS,
    Scorer,
    score_promo,
)

# ---------------------------------------------------------------------------
# Canonical source headers (mirror the real data/ CSVs and
# tests/test_part1_features_edge.py).
# ---------------------------------------------------------------------------

LEADS_HEADER = "promo_id,client_id,control_group,channel_sent,joined,join_date"
DNA_HEADER = (
    "client_id,segment,age_band,region,sec_class,inflow_type,online_shopper,"
    "tenure_years,digital_app_user,frugal_flag,investment_propensity_decile,"
    "email_valid,mobile_valid"
)
PRODUCT_HEADER = "client_id,product_code,product_type,open_date,status"
ADB_HEADER = "client_id,month,adb_php"
CONTACT_HEADER = "client_id,contact_date,campaign_id,channel"
NDB_HEADER = "client_id,flag_type,flag_date"
PART2_HEADER = "client_id,total_out,ext_outflow_ratio"
PROMO_HISTORY_HEADER = (
    "promo_id,promo_name,product_type,mechanic,threshold_php,reward,"
    "start_date,end_date,channels"
)

# The three training promos, each mapped to one of the known mechanics so the
# promo-history join resolves a mechanic the trained schema has a code for.
PROMO_MECHANICS = {
    "P001": ("TOP_UP", 500000),
    "P002": ("NEW_ACCOUNT", 1000),
    "P003": ("ADB_INCREASE", 50000),
}

# Treated leads spanning the three promos. Each (promo, client, joined) row is a
# control_group==0 lead. Across the whole population there are >=3 joiners and
# >=3 non-joiners so the internal cv=3 calibration sees both classes per fold.
# Two joiners and two non-joiners per promo => 6 joiners and 6 non-joiners.
_TREATED_LEADS: list[tuple[str, str, int]] = [
    ("P001", "C000001", 1),
    ("P001", "C000002", 1),
    ("P001", "C000003", 0),
    ("P001", "C000004", 0),
    ("P002", "C000005", 1),
    ("P002", "C000006", 1),
    ("P002", "C000007", 0),
    ("P002", "C000008", 0),
    ("P003", "C000009", 1),
    ("P003", "C000010", 1),
    ("P003", "C000011", 0),
    ("P003", "C000012", 0),
]

# Every distinct client that appears in a treated lead; each gets a matching row
# in the client-keyed sources so the feature blocks resolve.
_CLIENT_IDS = [client for _promo, client, _joined in _TREATED_LEADS]

# Small catalogs of valid Customer_DNA categorical values (mirror the known
# domains in tests/test_part1_features_edge.py) so the DNA encoder has real
# categories to learn codes for. Cycled across clients for mild variety.
_SEGMENTS = ["Mass", "Affluent"]
_AGE_BANDS = ["25-34", "35-44"]
_REGIONS = ["NCR", "Luzon"]
_SEC_CLASSES = ["B1", "C1"]
_INFLOW_TYPES = ["Salary", "Remittance"]
_ONLINE_SHOPPERS = ["Low", "Medium"]


def _write(path: Path, lines: list[str]) -> None:
    """Write ``lines`` (newline-joined, trailing newline) to ``path``."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sources(tmp_path: Path) -> Config:
    """Write minimal valid CSVs for all eight sources; return a wired Config.

    Builds a treated-lead population across P001/P002/P003 (>=3 joiners and >=3
    non-joiners) plus a matching row per client in every client-keyed source, so
    ``fit_transform`` assembles a complete multi-feature matrix and the model
    fits cleanly under ``cv=3``. No written path contains ``_answer_key``.
    """
    paths = {
        "promo_leads": tmp_path / "promo_leads.csv",
        "customer_dna": tmp_path / "customer_dna.csv",
        "product_ownership": tmp_path / "product_ownership.csv",
        "adb_monthly": tmp_path / "adb_monthly.csv",
        "contact_history": tmp_path / "contact_history.csv",
        "ndb": tmp_path / "ndb.csv",
        "features_part2": tmp_path / "features_part2.csv",
        "promo_history": tmp_path / "promo_history.csv",
    }

    # --- promo_leads: one treated row per (promo, client, joined). ---
    lead_rows = [LEADS_HEADER]
    for promo, client, joined in _TREATED_LEADS:
        lead_rows.append(f"{promo},{client},0,Email,{joined},2026-07-10")
    _write(paths["promo_leads"], lead_rows)

    # --- customer_dna: one row per client, cycling the small valid catalogs. ---
    dna_rows = [DNA_HEADER]
    for i, client in enumerate(_CLIENT_IDS):
        seg = _SEGMENTS[i % len(_SEGMENTS)]
        age = _AGE_BANDS[i % len(_AGE_BANDS)]
        region = _REGIONS[i % len(_REGIONS)]
        sec = _SEC_CLASSES[i % len(_SEC_CLASSES)]
        inflow = _INFLOW_TYPES[i % len(_INFLOW_TYPES)]
        shopper = _ONLINE_SHOPPERS[i % len(_ONLINE_SHOPPERS)]
        tenure = 1.0 + i
        digital = i % 2
        frugal = (i + 1) % 2
        decile = i % 10
        dna_rows.append(
            f"{client},{seg},{age},{region},{sec},{inflow},{shopper},"
            f"{tenure},{digital},{frugal},{decile},1,1"
        )
    _write(paths["customer_dna"], dna_rows)

    # --- product_ownership: one Active Deposit row per client, plus a Loan
    #     Active row for every other client so two active-count columns exist. ---
    product_rows = [PRODUCT_HEADER]
    for i, client in enumerate(_CLIENT_IDS):
        product_rows.append(f"{client},DEP-01,Deposit,2024-01-01,Active")
        if i % 2 == 0:
            product_rows.append(f"{client},LN-01,Loan,2024-01-01,Active")
    _write(paths["product_ownership"], product_rows)

    # --- adb_monthly: three ascending months per client so adb_trend is a
    #     real (non-degenerate) slope. ---
    adb_rows = [ADB_HEADER]
    for i, client in enumerate(_CLIENT_IDS):
        base = 100000 + 1000 * i
        adb_rows.append(f"{client},2026-01,{base}")
        adb_rows.append(f"{client},2026-02,{base + 500}")
        adb_rows.append(f"{client},2026-03,{base + 1500}")
    _write(paths["adb_monthly"], adb_rows)

    # --- contact_history: two contacts in distinct months per client. ---
    contact_rows = [CONTACT_HEADER]
    for client in _CLIENT_IDS:
        contact_rows.append(f"{client},2026-02-10,CMP100,Email")
        contact_rows.append(f"{client},2026-03-15,CMP101,SMS")
    _write(paths["contact_history"], contact_rows)

    # --- ndb: flag roughly half the clients to exercise both ndb_flag values. ---
    ndb_rows = [NDB_HEADER]
    for i, client in enumerate(_CLIENT_IDS):
        if i % 3 == 0:
            ndb_rows.append(f"{client},Loan delinquency,2026-01-01")
    _write(paths["ndb"], ndb_rows)

    # --- features_part2: one row per client with two numeric features. ---
    part2_rows = [PART2_HEADER]
    for i, client in enumerate(_CLIENT_IDS):
        part2_rows.append(f"{client},{1000.0 + i},{0.1 + 0.05 * i}")
    _write(paths["features_part2"], part2_rows)

    # --- promo_history: one row per training promo with its known mechanic. ---
    promo_rows = [PROMO_HISTORY_HEADER]
    for promo, (mechanic, threshold) in PROMO_MECHANICS.items():
        promo_rows.append(
            f"{promo},Promo {promo},Deposit,{mechanic},{threshold},reward,"
            "2026-02-01,2026-03-31,Email"
        )
    _write(paths["promo_history"], promo_rows)

    return Config(
        promo_leads_path=paths["promo_leads"],
        customer_dna_path=paths["customer_dna"],
        product_ownership_path=paths["product_ownership"],
        adb_monthly_path=paths["adb_monthly"],
        contact_history_path=paths["contact_history"],
        ndb_path=paths["ndb"],
        features_part2_path=paths["features_part2"],
        promo_history_path=paths["promo_history"],
    )


def _fit_pipeline(tmp_path: Path):
    """Write sources, load leads, assemble features, and fit the model.

    Returns ``(config, leads, X, model)`` where ``model`` is the fitted
    :class:`Calibrated_Model`. This is the realistic fitted model
    ``score_promo`` needs: its ``schema`` was learned over the very source files
    the Config points at, so ``Feature_Assembler.transform`` reproduces matching
    columns when ``score_promo`` re-reads them.
    """
    config = _write_sources(tmp_path)
    leads = Lead_Loader(config).load()
    assembler = Feature_Assembler(config)
    X, schema = assembler.fit_transform(leads)
    model = Model_Trainer(config).fit(X, leads["Join_Label"], schema)
    return config, leads, X, model


def test_scores_csv_header_is_six_columns_in_order_no_index(tmp_path: Path) -> None:
    """``scores.csv`` header is exactly the six fixed columns, no index column.

    ``Scorer.score_leads`` + ``write_scores`` persist the batch scores; the
    first CSV line must be exactly ``promo_id,client_id,p_join,top_driver_1,
    top_driver_2,top_driver_3`` and reading the file back with pandas must yield
    exactly those columns with no leading unnamed index column (Requirement 6.3).

    _Requirements: 6.3_
    """
    config, leads, X, model = _fit_pipeline(tmp_path)

    scorer = Scorer(model, config)
    scored = scorer.score_leads(leads, X)

    out_path = tmp_path / "outputs" / "scores.csv"
    scorer.write_scores(scored, out_path)

    assert out_path.exists()

    # The raw first line is exactly the six fixed columns in order.
    with open(out_path, newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header == SCORE_COLUMNS
    assert header == [
        "promo_id",
        "client_id",
        "p_join",
        "top_driver_1",
        "top_driver_2",
        "top_driver_3",
    ]

    # Reading back with pandas yields exactly those columns -- no "Unnamed: 0"
    # index column leaked in, confirming index=False (Requirement 6.3).
    reread = pd.read_csv(out_path)
    assert list(reread.columns) == SCORE_COLUMNS
    assert not any(str(column).startswith("Unnamed") for column in reread.columns)

    # One row per treated lead survives the round-trip.
    assert len(reread) == len(leads)


def test_score_promo_known_mechanic_matches_schema_and_has_drivers(
    tmp_path: Path,
) -> None:
    """score_promo returns per-client rows matching the schema, no retraining.

    With a known mechanic (TOP_UP), ``score_promo`` builds a feature matrix
    through ``Feature_Assembler.transform`` with the model's frozen schema, so
    it accepts a promo_dict carrying promo_id/mechanic/threshold_php and a
    clients_df and returns one row per client with ``p_join`` in ``[0, 1]`` and
    three top-driver columns. It applies the already-fitted model without
    retraining or recalibrating -- asserted by confirming the same
    ``Calibrated_Model`` instance (its calibrated predictor and booster objects)
    is unchanged after the call, and that scoring stays within ``[0, 1]``.

    _Requirements: 7.1, 7.2, 7.3, 7.5_
    """
    config, leads, _X, model = _fit_pipeline(tmp_path)

    # Capture the fitted model's internals so we can prove no retraining happened.
    calibrated_before = model.calibrated
    booster_before = model.booster

    # A few eligible clients that exist in the client-keyed sources.
    clients_df = pd.DataFrame({"client_id": _CLIENT_IDS[:4]})

    promo_dict = {
        "promo_id": "P999-NEW",
        "mechanic": "TOP_UP",  # a KNOWN mechanic
        "threshold_php": 250000,
    }

    # A known mechanic must NOT emit a warning; treat any warning as an error
    # for the duration of this call.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = score_promo(promo_dict, clients_df, model, config)

    # One row per eligible client, in the fixed score_promo column order.
    assert list(result.columns) == SCORE_PROMO_COLUMNS
    assert len(result) == len(clients_df)
    assert list(result["client_id"]) == _CLIENT_IDS[:4]

    # Every client's p_join is a calibrated probability in [0, 1] (Req 7.3).
    assert result["p_join"].between(0.0, 1.0).all()

    # Three top-driver columns are present and every driver name is a string
    # (Requirement 7.5); the drivers reference real trained-schema predictors.
    schema_columns = set(model.schema.columns)
    for position in ("top_driver_1", "top_driver_2", "top_driver_3"):
        assert position in result.columns
        for driver in result[position]:
            assert isinstance(driver, str)
            # A non-empty driver names an actual trained predictor; "" is the
            # pad for fewer than three non-zero contributions.
            assert driver == "" or driver in schema_columns

    # The model was applied as-is: its calibrated predictor and booster are the
    # exact same objects after scoring, i.e. nothing was retrained/recalibrated
    # (Requirement 7.3).
    assert model.calibrated is calibrated_before
    assert model.booster is booster_before


def test_score_promo_unseen_mechanic_warns_and_returns_valid_probabilities(
    tmp_path: Path,
) -> None:
    """An unseen mechanic emits a warning yet still scores every client in [0, 1].

    The mechanic ``"MYSTERY_DEAL"`` is not among ``KNOWN_MECHANICS``, so
    ``score_promo`` must emit a warning that predictions are less reliable for
    unseen mechanics (Requirement 7.4) while still returning one calibrated
    ``p_join`` in ``[0, 1]`` for every eligible client.

    _Requirements: 7.4_
    """
    config, leads, _X, model = _fit_pipeline(tmp_path)

    clients_df = pd.DataFrame({"client_id": _CLIENT_IDS})

    promo_dict = {
        "promo_id": "P888-UNSEEN",
        "mechanic": "MYSTERY_DEAL",  # NOT a known mechanic
        "threshold_php": 123456,
    }

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = score_promo(promo_dict, clients_df, model, config)

    # At least one warning mentioning the unseen-mechanic reliability caveat.
    assert len(caught) >= 1
    messages = " ".join(str(w.message).lower() for w in caught)
    assert "mechanic" in messages
    assert "unseen" in messages or "less reliable" in messages

    # Every eligible client still gets a calibrated p_join in [0, 1] (Req 7.4).
    assert len(result) == len(clients_df)
    assert result["p_join"].between(0.0, 1.0).all()
    assert result["p_join"].notna().all()
