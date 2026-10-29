"""CLI entry point wiring the full Part3_Segments_Pipeline.

Parses the input/output path overrides onto a :class:`Config`, then runs the
pipeline in order (Requirement 5.1):

1. :func:`loader.load` -- load and validate the five inputs.
2. :func:`segments.assign` + :func:`segments.write` -- assign a segment to every
   Lead and write the per-lead Segments_File.
3. :func:`validation.build` + :func:`validation.write` -- build the per-cell
   Segment_Summary and write the Segment_Summary_File.
4. Print one line per (promo, segment) summary cell (Requirement 5.2).

The Input_Loader is the only stage permitted to halt the pipeline: it validates
before any output is produced, so a missing or malformed input file raises
``FileNotFoundError`` / ``ValueError`` out of :func:`main` before
:func:`segments.write` runs, leaving ``outputs/`` untouched and printing no
summary (Requirement 5.4). Empty ``actual_join_rate`` / ``top_driver_1`` fields
are rendered as 0 or blank when printed (Requirement 5.3).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from part3_segments import loader, segments, validation
from part3_segments.config import Config


def _parse_config(argv: list[str] | None) -> Config:
    """Parse the pipeline's path-override arguments into a :class:`Config`.

    The seven optional overrides map onto the :class:`Config` path fields and
    default to its canonical paths, matching the part2_network convention
    (Requirements 1.1, 3.1, 4.6, 5.1). ``argv`` of ``None`` leaves argparse to
    read ``sys.argv[1:]``.
    """
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="part3_segments",
        description="Run the Part 3 segment-assignment pipeline and print the summary.",
    )
    parser.add_argument(
        "--scores",
        default=defaults.scores_path,
        type=Path,
        help="Path to the scored-leads CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--features",
        default=defaults.features_path,
        type=Path,
        help="Path to the Part 2 features CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--adb-monthly",
        default=defaults.adb_monthly_path,
        type=Path,
        help="Path to the monthly ADB CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-history",
        default=defaults.promo_history_path,
        type=Path,
        help="Path to the promo-history CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-leads",
        default=defaults.promo_leads_path,
        type=Path,
        help="Path to the promo-leads CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--segments-out",
        default=defaults.segments_out_path,
        type=Path,
        help="Path for the per-lead segments output CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--summary-out",
        default=defaults.summary_out_path,
        type=Path,
        help="Path for the per-cell summary output CSV (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    return Config(
        scores_path=args.scores,
        features_path=args.features,
        adb_monthly_path=args.adb_monthly,
        promo_history_path=args.promo_history,
        promo_leads_path=args.promo_leads,
        segments_out_path=args.segments_out,
        summary_out_path=args.summary_out,
    )


def _render(value: object) -> str:
    """Render a summary field for printing, blanking empty rate/driver values.

    An empty ``actual_join_rate`` arrives as NaN and an empty most-common
    ``top_driver_1`` arrives as the empty string; both are printed as a blank
    field (Requirement 5.3). All other values are rendered with ``str``.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value)


def _print_summary(summary: pd.DataFrame) -> None:
    """Print one line per (promo, segment) summary cell.

    Each line carries the seven summary fields in order: ``promo_id``,
    ``segment``, ``n_clients``, ``mean_p_join``, ``expected_joiners``,
    ``actual_join_rate``, and ``top_driver_1`` (Requirement 5.2). An empty
    ``actual_join_rate`` or ``top_driver_1`` is printed as a blank field
    (Requirement 5.3).
    """
    for row in summary.itertuples(index=False):
        fields = [
            _render(row.promo_id),
            _render(row.segment),
            _render(row.n_clients),
            _render(row.mean_p_join),
            _render(row.expected_joiners),
            _render(row.actual_join_rate),
            _render(row.top_driver_1),
        ]
        print("\t".join(fields))


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end pipeline and return a process exit code.

    Parses ``argv`` (``None`` reads ``sys.argv[1:]``) into a :class:`Config`,
    then runs the pipeline in order (Requirement 5.1):

    1. ``loader.load`` -- load and validate the five inputs.
    2. ``segments.assign`` + ``segments.write`` -- assign segments and write the
       per-lead Segments_File.
    3. ``validation.build`` + ``validation.write`` -- build and write the
       per-cell Segment_Summary_File.
    4. ``_print_summary`` -- print one line per summary cell (Requirements 5.2,
       5.3).

    The loader validates before anything is written, so a missing or malformed
    input raises out of :func:`main` before :func:`segments.write` and no output
    is produced or printed (Requirement 5.4). A successful run returns 0.
    """
    cfg = _parse_config(argv)

    # The loader is the only gate: any error here propagates out of main before
    # the Segmenter writes anything (Requirement 5.4).
    frames = loader.load(cfg)

    leads = segments.assign(frames)
    segments.write(leads, cfg.segments_out_path)

    summary = validation.build(leads, frames["promo_leads"])
    validation.write(summary, cfg.summary_out_path)

    _print_summary(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
