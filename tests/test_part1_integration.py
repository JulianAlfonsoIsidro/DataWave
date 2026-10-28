"""Integration / smoke test for the full Part1_Optin_Pipeline (task 12.1).

Runs :func:`part1_optin.main.main` end-to-end against the *real* data files in
``data/`` plus the committed ``outputs/features_part2.csv``, writing the model
artifact and scores file to a throwaway ``tmp_path`` location via the CLI path
overrides so the committed ``outputs/`` artifacts are never clobbered.

This is a smoke-level check: it asserts the pipeline exits 0, prints a
three-promo leave-one-promo-out report, writes a reloadable XGBoost booster
artifact plus its sidecar, and writes a well-formed ``scores.csv`` with one row
per treated lead in the fixed six-column layout, sorted by ``promo_id`` then
``client_id``. It does not re-derive every feature value (the unit and property
suites cover that).

The absolute safety rule (Requirement 2.14) is enforced at the I/O boundary: a
recorder wraps ``pandas.read_csv`` and the builtin ``open`` for the whole run
and asserts that no path containing the substring ``_answer_key`` was ever
opened. The ``data/`` directory on disk *does* contain answer-key files, so
this is a live check that the pipeline stays away from them.

No path in this module is spelled as a literal ``*_answer_key*`` reference; the
forbidden marker is imported from ``part1_optin.config`` and any path used to
prove the recorder would flag a violation is built by concatenating that
imported marker.

Validates: Requirements 2.14, 6.1, 6.3, 7.6.
"""

from __future__ import annotations

import builtins
import re
from pathlib import Path

import pandas as pd
import pytest
import xgboost

from part1_optin.config import ANSWER_KEY_MARKER, Config
from part1_optin.leads import Lead_Loader
from part1_optin.main import main

# Repo root is two levels up from this test file: tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"

# The eight real inputs the pipeline reads end-to-end.
PROMO_LEADS = DATA_DIR / "promo_leads.csv"
CUSTOMER_DNA = DATA_DIR / "customer_dna.csv"
PRODUCT_OWNERSHIP = DATA_DIR / "product_ownership.csv"
ADB_MONTHLY = DATA_DIR / "adb_monthly.csv"
CONTACT_HISTORY = DATA_DIR / "contact_history.csv"
NDB = DATA_DIR / "ndb.csv"
FEATURES_PART2 = OUTPUTS_DIR / "features_part2.csv"
PROMO_HISTORY = DATA_DIR / "promo_history.csv"

_REQUIRED_INPUTS = [
    PROMO_LEADS,
    CUSTOMER_DNA,
    PRODUCT_OWNERSHIP,
    ADB_MONTHLY,
    CONTACT_HISTORY,
    NDB,
    FEATURES_PART2,
    PROMO_HISTORY,
]

# If any real input is absent the smoke test cannot run; skip rather than fail.
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in _REQUIRED_INPUTS),
    reason="real data files (data/*.csv, outputs/features_part2.csv) not present",
)

# The fixed Scores_File column order (Requirement 6.3).
_EXPECTED_SCORE_COLUMNS = [
    "promo_id",
    "client_id",
    "p_join",
    "top_driver_1",
    "top_driver_2",
    "top_driver_3",
]

# Matches a printed per-promo held-out header, e.g. "Held-out promo: P001".
_HELD_OUT_RE = re.compile(r"Held-out promo:\s*(P00[123])")


class _ReadRecorder:
    """Record every path passed to ``pandas.read_csv`` / builtin ``open``.

    Installed over both readers for the duration of the end-to-end run;
    afterwards :meth:`answer_key_offenders` reports any recorded path that
    contains the forbidden marker, so Requirement 2.14 is checked against every
    real I/O the pipeline performed.
    """

    def __init__(self) -> None:
        self.paths: list[str] = []
        self._real_read_csv = pd.read_csv
        self._real_open = builtins.open

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "_ReadRecorder":
        monkeypatch.setattr(pd, "read_csv", self._record_read_csv)
        monkeypatch.setattr(builtins, "open", self._record_open)
        return self

    def _record_read_csv(self, filepath_or_buffer, *args, **kwargs):
        self._record(filepath_or_buffer)
        return self._real_read_csv(filepath_or_buffer, *args, **kwargs)

    def _record_open(self, file, *args, **kwargs):
        self._record(file)
        return self._real_open(file, *args, **kwargs)

    def _record(self, target) -> None:
        # Only path-like targets carry a filesystem name that could violate the
        # prohibition; file descriptors / buffers are ignored.
        if isinstance(target, (str, Path)):
            self.paths.append(str(target))

    def answer_key_offenders(self) -> list[str]:
        return [p for p in self.paths if ANSWER_KEY_MARKER in p]


def _run_pipeline_to_tmp(tmp_path: Path, recorder: _ReadRecorder) -> int:
    """Run ``main`` against the real inputs, writing outputs under ``tmp_path``.

    Real inputs are passed explicitly (resolved from the repo root so the test
    is cwd-robust); the model artifact and scores file are redirected into
    ``tmp_path`` so the committed ``outputs/`` artifacts are untouched. The
    recorder is already installed over the readers by the caller.
    """
    model_out = tmp_path / "model_part1.json"
    scores_out = tmp_path / "scores.csv"
    return main(
        [
            "--promo-leads", str(PROMO_LEADS),
            "--customer-dna", str(CUSTOMER_DNA),
            "--product-ownership", str(PRODUCT_OWNERSHIP),
            "--adb", str(ADB_MONTHLY),
            "--contact-history", str(CONTACT_HISTORY),
            "--ndb", str(NDB),
            "--features-part2", str(FEATURES_PART2),
            "--promo-history", str(PROMO_HISTORY),
            "--model-out", str(model_out),
            "--scores-out", str(scores_out),
        ]
    )


def test_pipeline_end_to_end_against_real_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full pipeline runs clean and writes well-formed artifacts (6.1, 6.3, 7.6).

    Drives ``main`` with explicit real input paths and tmp output paths while a
    recorder wraps every ``pandas.read_csv`` / ``open``. Asserts exit code 0,
    the three-promo LOPO report printed, the booster artifact reloads, the
    sidecar exists, and ``scores.csv`` carries the six fixed columns sorted by
    ``promo_id`` then ``client_id`` with one row per treated lead -- and that no
    answer-key path was opened during the run (Requirement 2.14).
    """
    recorder = _ReadRecorder().install(monkeypatch)

    model_out = tmp_path / "model_part1.json"
    scores_out = tmp_path / "scores.csv"
    sidecar_out = model_out.with_suffix(".sidecar.json")

    exit_code = _run_pipeline_to_tmp(tmp_path, recorder)

    # 7.6: a fully successful run returns exit code 0.
    assert exit_code == 0, "pipeline did not exit cleanly against the real data"

    # 2.14: no path containing the answer-key marker was opened during the run.
    offenders = recorder.answer_key_offenders()
    assert not offenders, (
        f"Requirement 2.14 violated: the run opened answer-key path(s) {offenders!r}"
    )
    # The recorder must have observed real reads, else the check is vacuous.
    assert recorder.paths, "expected the recorder to capture at least one read"

    # 6.1: the model artifact and its sidecar were written, and the artifact
    # reloads as a valid XGBoost booster that predicts.
    assert model_out.exists(), "model artifact was not written"
    assert sidecar_out.exists(), "model sidecar was not written"

    reloaded = xgboost.Booster()
    reloaded.load_model(str(model_out))
    assert isinstance(reloaded, xgboost.Booster)

    # 6.3: scores.csv exists with exactly the six fixed columns in order.
    assert scores_out.exists(), "scores file was not written"
    scores = pd.read_csv(scores_out)
    assert list(scores.columns) == _EXPECTED_SCORE_COLUMNS

    # 6.5-style smoke check: rows are sorted by promo_id then client_id.
    resorted = scores.sort_values(["promo_id", "client_id"]).reset_index(drop=True)
    assert scores.reset_index(drop=True).equals(resorted), (
        "scores.csv is not sorted by promo_id then client_id"
    )

    # 6.6: exactly one row per treated lead. Cross-check the row count against
    # an independent Lead_Loader.load() over the same real promo-leads file.
    treated = Lead_Loader(Config(promo_leads_path=PROMO_LEADS)).load()
    assert len(scores) == len(treated), (
        f"scores rows ({len(scores)}) != treated leads ({len(treated)})"
    )

    # p_join values are within the inclusive unit interval (6.4 source).
    assert (scores["p_join"] >= 0.0).all()
    assert (scores["p_join"] <= 1.0).all()

    # The three-promo LOPO report printed, one held-out header per promo (7.6).
    printed = capsys.readouterr().out
    held_out = {m.group(1) for m in _HELD_OUT_RE.finditer(printed)}
    assert held_out == {"P001", "P002", "P003"}, (
        f"expected a LOPO held-out section for each promo, saw {sorted(held_out)}"
    )

    # The committed real outputs must be untouched by this test (we wrote to
    # tmp_path, not outputs/).
    assert model_out.parent == tmp_path


def test_recorder_would_flag_a_forbidden_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorder genuinely detects an answer-key read (anti-vacuous guard).

    Proves the Requirement 2.14 assertion in the end-to-end test is not vacuous:
    a synthetic read of a path built from the imported marker is recorded and
    flagged as an offender. The file need not exist -- the recorder captures the
    path before any read error.
    """
    recorder = _ReadRecorder().install(monkeypatch)

    forbidden = Path("data") / (ANSWER_KEY_MARKER + "_clients.csv")
    try:
        pd.read_csv(forbidden)
    except Exception:
        pass

    # The marker path is flagged. ``pandas.read_csv`` opens the file via the
    # (also recorded) builtin ``open``, so the path may be captured more than
    # once; assert the offender is present and that every offender is that one
    # marker path rather than pinning an exact count.
    offenders = recorder.answer_key_offenders()
    assert str(forbidden) in offenders
    assert set(offenders) == {str(forbidden)}
