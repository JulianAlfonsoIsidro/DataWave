"""Example/edge unit tests for the Part1_Optin CLI wiring (task 11.2).

Targeted (non-Hypothesis) tests for :mod:`part1_optin.main`, covering:

- CLI path overrides map onto the :class:`~part1_optin.config.Config` before any
  load or write: ``_config_from_args(_parse_args([...]))`` with all ten path
  flags set to custom paths returns a ``Config`` whose fields equal those
  ``Path`` values (Requirement 7.8). This is a pure, fast check.
- A successful end-to-end run returns exit code ``0`` and writes both the model
  artifact and the scores file (Requirements 7.6, 6.1, 6.3). A tiny but complete
  set of all eight sources is built in ``tmp_path`` with enough treated
  two-class leads across P001/P002/P003 for the internal ``cv=3`` calibration.
- A mid-pipeline failure (a non-existent ``--promo-leads`` path makes
  ``Lead_Loader`` raise at the very first step) yields a non-zero exit, a stderr
  message naming the failing step, and leaves no ``model_part1.json`` or
  ``scores.csv`` written at the override output paths (Requirements 6.2, 7.7).

The success test reuses the eight-source fixture builder from
``tests/test_part1_scoring_unit.py`` (imported as ``_write_sources``) so the
treated-lead population spans P001/P002/P003 with at least three joiners and
three non-joiners. No fixture or path references a ``*_answer_key*`` file
(Requirement 2.14).
"""

from __future__ import annotations

from pathlib import Path

from part1_optin.config import Config
from part1_optin.main import _config_from_args, _parse_args, main

# Reuse the complete eight-source fixture builder from the scoring unit tests so
# the success case runs a real (tiny) pipeline end to end.
from tests.test_part1_scoring_unit import _write_sources


def test_cli_overrides_map_onto_config(tmp_path: Path) -> None:
    """All ten path flags override the matching ``Config`` field (Req 7.8).

    ``_parse_args`` followed by ``_config_from_args`` must land each supplied
    ``--...`` path on the corresponding frozen ``Config`` field as a ``Path``,
    so the overrides are applied before the pipeline loads inputs or writes
    outputs. This is a pure/fast test -- no files are read or written.

    _Requirements: 7.8_
    """
    overrides = {
        "promo_leads_path": tmp_path / "in_leads.csv",
        "customer_dna_path": tmp_path / "in_dna.csv",
        "product_ownership_path": tmp_path / "in_products.csv",
        "adb_monthly_path": tmp_path / "in_adb.csv",
        "contact_history_path": tmp_path / "in_contacts.csv",
        "ndb_path": tmp_path / "in_ndb.csv",
        "features_part2_path": tmp_path / "in_part2.csv",
        "promo_history_path": tmp_path / "in_promo.csv",
        "model_output_path": tmp_path / "out_model.json",
        "scores_output_path": tmp_path / "out_scores.csv",
    }

    argv = [
        "--promo-leads", str(overrides["promo_leads_path"]),
        "--customer-dna", str(overrides["customer_dna_path"]),
        "--product-ownership", str(overrides["product_ownership_path"]),
        "--adb", str(overrides["adb_monthly_path"]),
        "--contact-history", str(overrides["contact_history_path"]),
        "--ndb", str(overrides["ndb_path"]),
        "--features-part2", str(overrides["features_part2_path"]),
        "--promo-history", str(overrides["promo_history_path"]),
        "--model-out", str(overrides["model_output_path"]),
        "--scores-out", str(overrides["scores_output_path"]),
    ]

    config = _config_from_args(_parse_args(argv))

    assert isinstance(config, Config)
    for field, expected_path in overrides.items():
        actual = getattr(config, field)
        assert actual == expected_path
        assert isinstance(actual, Path)


def test_main_successful_run_returns_zero_and_writes_outputs(tmp_path: Path) -> None:
    """A full run returns 0 and writes the model artifact and scores file.

    The eight-source fixture (reused from the scoring unit tests) gives a treated
    population across P001/P002/P003 with >=3 joiners and >=3 non-joiners, so
    the internal ``cv=3`` calibration fits cleanly. Pointing ``--model-out`` and
    ``--scores-out`` at ``tmp_path`` and running the CLI must return exit code 0
    and leave both ``model_part1.json`` and ``scores.csv`` on disk
    (Requirements 7.6, 6.1, 6.3).

    _Requirements: 7.6_
    """
    config = _write_sources(tmp_path)

    model_out = tmp_path / "outputs" / "model_part1.json"
    scores_out = tmp_path / "outputs" / "scores.csv"

    argv = [
        "--promo-leads", str(config.promo_leads_path),
        "--customer-dna", str(config.customer_dna_path),
        "--product-ownership", str(config.product_ownership_path),
        "--adb", str(config.adb_monthly_path),
        "--contact-history", str(config.contact_history_path),
        "--ndb", str(config.ndb_path),
        "--features-part2", str(config.features_part2_path),
        "--promo-history", str(config.promo_history_path),
        "--model-out", str(model_out),
        "--scores-out", str(scores_out),
    ]

    exit_code = main(argv)

    assert exit_code == 0
    assert model_out.exists()
    assert scores_out.exists()


def test_main_failure_nonzero_exit_names_step_and_writes_no_outputs(
    tmp_path: Path, capsys
) -> None:
    """A first-step failure exits non-zero, names the step, writes no outputs.

    Pointing ``--promo-leads`` at a non-existent file makes ``Lead_Loader.load``
    (the first pipeline step) raise ``FileNotFoundError``. ``main`` must catch
    it, print a stderr message naming the failing step ("load treated leads"),
    return a non-zero exit code, and leave neither ``model_part1.json`` nor
    ``scores.csv`` written at the override output paths (Requirements 6.2, 7.7).

    _Requirements: 6.2, 7.7_
    """
    # A valid set of the other sources, then clobber promo-leads with a path
    # that does not exist so only the first step fails.
    config = _write_sources(tmp_path)
    missing_leads = tmp_path / "does_not_exist_promo_leads.csv"
    assert not missing_leads.exists()

    model_out = tmp_path / "outputs" / "model_part1.json"
    scores_out = tmp_path / "outputs" / "scores.csv"

    argv = [
        "--promo-leads", str(missing_leads),
        "--customer-dna", str(config.customer_dna_path),
        "--product-ownership", str(config.product_ownership_path),
        "--adb", str(config.adb_monthly_path),
        "--contact-history", str(config.contact_history_path),
        "--ndb", str(config.ndb_path),
        "--features-part2", str(config.features_part2_path),
        "--promo-history", str(config.promo_history_path),
        "--model-out", str(model_out),
        "--scores-out", str(scores_out),
    ]

    exit_code = main(argv)

    # Non-zero exit (Requirement 7.7).
    assert exit_code != 0

    # stderr names the failing step; the first step is "load treated leads".
    captured = capsys.readouterr()
    assert "load treated leads" in captured.err

    # No outputs written anywhere under the override paths (Requirements 6.2, 7.7).
    assert not model_out.exists()
    assert not scores_out.exists()
    # The sidecar artifacts the model save would have produced are also absent.
    assert not model_out.with_suffix(".sidecar.json").exists()
