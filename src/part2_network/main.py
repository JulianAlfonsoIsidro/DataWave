"""CLI entry point wiring the full Part2_Network_Pipeline.

Parses the input/output path overrides, then runs the pipeline in order:
validate and load the Transactions_File (:func:`reader.read`), build and write
the Features_File (:func:`features.build` / :func:`features.write`), then read
the Promo_Leads_File, select the P001 Treated_Leads, and print the validation
report (:mod:`validation`).

The Transaction_Reader is the only stage permitted to halt the pipeline: it
validates before any output is produced, so a bad Transactions_File raises
``FileNotFoundError`` / ``ValueError`` before :func:`features.write` runs and
``outputs/`` is left untouched (Requirement 1). Such errors are caught here,
reported to stderr, and turned into a non-zero exit code; a successful run
returns 0 (Requirements 1.1, 8.1, 9.1).
"""

from __future__ import annotations

import argparse
import sys

from part2_network import features, reader, validation
from part2_network.config import Config


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the pipeline's path-override arguments.

    The three optional overrides map onto the :class:`Config` fields and
    default to its canonical paths (Requirements 1.1, 8.1, 9.1). ``argv`` of
    ``None`` leaves argparse to read ``sys.argv[1:]``.
    """
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="part2_network",
        description="Run the Part 2 network feature pipeline and promo report.",
    )
    parser.add_argument(
        "--transactions",
        default=defaults.transactions_path,
        help="Path to the transactions CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-leads",
        default=defaults.promo_leads_path,
        help="Path to the promo-leads CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        default=defaults.output_path,
        help="Path for the features output CSV (default: %(default)s).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end pipeline and return a process exit code.

    Parses ``argv`` (``None`` reads ``sys.argv[1:]``) into the transactions,
    promo-leads, and output paths, then runs the pipeline in order:

    1. ``reader.read`` -- validate and load the Transactions_File.
    2. ``features.build`` + ``features.write`` -- assemble and write the
       Features_File.
    3. ``validation.read_leads`` / ``select_treated_leads`` / ``print_report``
       -- select the P001 Treated_Leads and print the quartile/join-rate report.

    The reader validates before anything is written, so a missing or malformed
    Transactions_File raises before :func:`features.write` and no output file is
    produced (Requirement 1). Those reader errors are caught, reported to
    stderr, and mapped to exit code 1; a successful run returns 0.
    """
    args = _parse_args(argv)

    try:
        txns = reader.read(args.transactions)
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    feature_frame = features.build(txns)
    features.write(feature_frame, args.out)

    leads = validation.read_leads(args.promo_leads)
    treated_leads = validation.select_treated_leads(leads)
    validation.print_report(treated_leads, feature_frame)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
