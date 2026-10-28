"""CLI entry point wiring the full Part1_Optin_Pipeline.

Parses the input/output path overrides into a :class:`Config`, then runs the
pipeline in order:

1. ``Lead_Loader.load`` -- load and select the treated P001/P002/P003 leads
   (the first halt gate; a missing file or zero treated leads stops the run
   before any output).
2. ``Feature_Assembler.fit_transform`` -- assemble the feature matrix ``X`` and
   learn the ``FeatureSchema``; the leads' ``Join_Label`` is the target ``y``
   and their ``promo_id`` column drives the LOPO folds.
3. ``Validator.run`` + ``Validator.print_report`` -- validation report
   (printed, produces no file output): the headline StratifiedGroupKFold
   metrics first, then the leave-one-promo-out cold-start block.
4. ``Model_Trainer.fit`` -- fit the FINAL calibrated model on ALL treated
   leads.
5. ``Scorer.score_leads`` (+ the ``Explainer`` it drives) -- calibrated-score
   every treated lead with its top-3 SHAP drivers.
6. ``Calibrated_Model.save`` + ``Scorer.write_scores`` -- the ONLY output-
   producing steps, run LAST so nothing is written until the final fit and
   scoring succeed (Requirements 6.2, 7.7).

Order is critical (Requirements 6.2, 7.7): no outputs are written until the
final fit succeeds, so any exception before the save/write steps leaves
``outputs/`` untouched. Each step is wrapped so a failure is reported to stderr
naming the failing step and mapped to a non-zero exit code; a fully successful
run returns 0 (Requirements 7.6, 7.7).

The design mirrors ``part2_network/main.py`` conventions: absolute imports,
argparse path overrides onto the :class:`Config` fields, a ``main(argv) -> int``
entry point, and ``raise SystemExit(main())`` at module scope.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from part1_optin.config import Config
from part1_optin.features import Feature_Assembler
from part1_optin.leads import Lead_Loader
from part1_optin.model import Model_Trainer
from part1_optin.scoring import Scorer
from part1_optin.validation import Validator


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the pipeline's path-override arguments.

    The optional overrides map onto the :class:`Config` fields and default to
    its canonical paths (Requirement 7.8). ``argv`` of ``None`` leaves argparse
    to read ``sys.argv[1:]``.
    """
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="part1_optin",
        description="Run the Part 1 opt-in propensity pipeline.",
    )
    parser.add_argument(
        "--promo-leads",
        default=defaults.promo_leads_path,
        help="Path to the promo-leads CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--customer-dna",
        default=defaults.customer_dna_path,
        help="Path to the customer-DNA CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--product-ownership",
        default=defaults.product_ownership_path,
        help="Path to the product-ownership CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--adb",
        default=defaults.adb_monthly_path,
        help="Path to the monthly ADB CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--contact-history",
        default=defaults.contact_history_path,
        help="Path to the contact-history CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--ndb",
        default=defaults.ndb_path,
        help="Path to the NDB CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--features-part2",
        default=defaults.features_part2_path,
        help="Path to the Part 2 features CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-history",
        default=defaults.promo_history_path,
        help="Path to the promo-history CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--model-out",
        default=defaults.model_output_path,
        help="Path for the booster model output JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--scores-out",
        default=defaults.scores_output_path,
        help="Path for the scores output CSV (default: %(default)s).",
    )
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> Config:
    """Build a :class:`Config` from parsed CLI args (Requirement 7.8).

    Each override is coerced to :class:`~pathlib.Path` so a string passed on the
    command line and a ``Path`` default land as the same type on the frozen
    ``Config``, which is then used for both load and write.
    """
    return Config(
        promo_leads_path=Path(args.promo_leads),
        customer_dna_path=Path(args.customer_dna),
        product_ownership_path=Path(args.product_ownership),
        adb_monthly_path=Path(args.adb),
        contact_history_path=Path(args.contact_history),
        ndb_path=Path(args.ndb),
        features_part2_path=Path(args.features_part2),
        promo_history_path=Path(args.promo_history),
        model_output_path=Path(args.model_out),
        scores_output_path=Path(args.scores_out),
    )


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end pipeline and return a process exit code.

    Parses ``argv`` (``None`` reads ``sys.argv[1:]``) into a :class:`Config`,
    then runs the pipeline in order: load the treated leads, assemble the
    feature matrix and schema, print the LOPO validation report, fit the final
    calibrated model on all treated leads, score every treated lead, and only
    then write the model artifact and scores file (Requirements 6.2, 7.6, 7.7,
    7.8).

    No output is produced until the final fit and scoring succeed, so a failure
    in any earlier step leaves ``outputs/`` untouched. Any step exception is
    caught, reported to stderr naming the failing step, and mapped to exit code
    1; a fully successful run returns 0.
    """
    args = _parse_args(argv)
    config = _config_from_args(args)

    # Each step runs under its own label so a failure can be reported to stderr
    # naming the stage that failed (Requirement 7.7). The two output-producing
    # steps (save model, write scores) run LAST, so any earlier failure leaves
    # outputs/ untouched (Requirements 6.2, 7.7).
    step = "load treated leads"
    try:
        leads = Lead_Loader(config).load()

        step = "assemble features"
        X, schema = Feature_Assembler(config).fit_transform(leads)
        y = leads["Join_Label"]
        promo_ids = leads["promo_id"]
        client_ids = leads["client_id"]

        step = "run validation"
        result = Validator(config).run(X, y, promo_ids, schema, client_ids)
        Validator(config).print_report(result)

        step = "fit final model"
        model = Model_Trainer(config).fit(X, y, schema)

        step = "score leads"
        scorer = Scorer(model, config)
        scored = scorer.score_leads(leads, X)

        # Output-producing steps run last so nothing is written unless the
        # final fit and scoring above succeeded (Requirements 6.2, 7.7).
        step = "write model artifact"
        model.save(config.model_output_path)

        step = "write scores"
        scorer.write_scores(scored, config.scores_output_path)
    except Exception as error:  # noqa: BLE001 - report any step failure
        print(f"error during step '{step}': {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
