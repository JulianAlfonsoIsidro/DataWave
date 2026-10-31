"""Entry point and Reporter for the Part4_Cards_Pipeline.

Parses the input/output path overrides onto a :class:`Config`, then runs the
pipeline in order (Requirement 6.1):

1. :func:`loader.load` -- load and validate the seven inputs.
2. :func:`classify.classify` -- per-Lead exclusion, best_channel, and the
   control/sendable split.
3. :func:`cards.build_cards_from_classified` -- build one Card per Cell.

Only after all three complete without error does the Reporter produce output
(Requirement 6.1):

- Write ``outputs/cards.json`` as a JSON list with exactly one Card per Cell,
  creating ``outputs/`` first if absent (Requirement 6.2).
- Write one ``outputs/leads/<promo_id>_<segment_slug>.csv`` per Cell, creating
  ``outputs/leads/`` first if absent; ``segment_slug`` is the segment lowercased
  with every run of one or more non-alphanumeric characters replaced by a single
  underscore; columns ``client_id``, ``best_channel``, ``p_join``, ``control``,
  one row per Sendable_Lead, ``control`` always 0, no Control or Excluded Leads
  (Requirements 6.3, 6.4).
- Print one summary line per Card: ``promo_id``, ``segment``, ``n_clients``,
  ``sendable_count``, ``expected_joiners``, ``expected_value``, ``action``
  (Requirement 6.5).

The Input_Loader is the only stage permitted to halt the pipeline: it validates
before any output is produced, so a missing or malformed input raises out of
:func:`main` before any output directory or file is created and before anything
is printed, leaving ``outputs/`` untouched (Requirement 6.6). The module ends
with the standard ``if __name__ == "__main__": raise SystemExit(main())`` guard,
so the package runs as ``python -m part4_cards.main`` with ``PYTHONPATH=src``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from . import loader
from .cards import build_cards_from_classified
from .classify import classify
from .config import Config

# Float rounding for the serialized Card (design "Reporter" section): expected
# joiners / value / cost and the range bounds to 2 decimals, probabilities to 4.
_MONEY_FIELDS = (
    "expected_joiners",
    "joiners_90_low",
    "joiners_90_high",
    "total_channel_cost",
    "expected_value",
)

# Columns of each per-Cell sendable-lead CSV (Requirement 6.4).
_LEADS_COLUMNS = ["client_id", "best_channel", "p_join", "control"]


def _parse_config(argv: list[str] | None) -> Config:
    """Parse the pipeline's path-override arguments into a :class:`Config`.

    The nine optional overrides map onto the :class:`Config` path fields and
    default to its canonical paths, matching the part3_segments convention
    (Requirements 1.1, 6.1). ``argv`` of ``None`` leaves argparse to read
    ``sys.argv[1:]``.
    """
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="part4_cards",
        description="Run the Part 4 action-cards pipeline and print the summary.",
    )
    parser.add_argument(
        "--segments",
        default=defaults.segments_path,
        type=Path,
        help="Path to the Part 3 segments CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--segment-summary",
        default=defaults.segment_summary_path,
        type=Path,
        help="Path to the Part 3 segment-summary CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--ndb",
        default=defaults.ndb_path,
        type=Path,
        help="Path to the national do-not-contact CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--contact-history",
        default=defaults.contact_history_path,
        type=Path,
        help="Path to the contact-history CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--channel-costs",
        default=defaults.channel_costs_path,
        type=Path,
        help="Path to the channel-costs CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--customer-dna",
        default=defaults.customer_dna_path,
        type=Path,
        help="Path to the customer-DNA CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-history",
        default=defaults.promo_history_path,
        type=Path,
        help="Path to the promo-history CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--cards-out",
        default=defaults.cards_out_path,
        type=Path,
        help="Path for the cards JSON output (default: %(default)s).",
    )
    parser.add_argument(
        "--leads-out-dir",
        default=defaults.leads_out_dir,
        type=Path,
        help="Directory for the per-Cell sendable-lead CSVs (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    return Config(
        segments_path=args.segments,
        segment_summary_path=args.segment_summary,
        ndb_path=args.ndb,
        contact_history_path=args.contact_history,
        channel_costs_path=args.channel_costs,
        customer_dna_path=args.customer_dna,
        promo_history_path=args.promo_history,
        cards_out_path=args.cards_out,
        leads_out_dir=args.leads_out_dir,
    )


def _segment_slug(segment: str) -> str:
    """Slugify a segment label for the per-Cell lead CSV filename.

    The segment is lowercased and every run of one or more non-alphanumeric
    characters is replaced by a single underscore (Requirement 6.3).
    """
    return re.sub(r"[^a-z0-9]+", "_", str(segment).lower())


def _round_card(card: dict) -> dict:
    """Return a copy of the Card with its float fields rounded for output.

    Money / count-estimate fields and the range bounds are rounded to 2
    decimals (design "Reporter" section); all other fields pass through
    unchanged.
    """
    rounded = dict(card)
    for field in _MONEY_FIELDS:
        if field in rounded:
            rounded[field] = round(float(rounded[field]), 2)
    return rounded


def _write_cards(cards: list[dict], cards_out_path: Path) -> None:
    """Write the Cards_File as a JSON list, one Card per Cell (Requirement 6.2).

    Creates the output directory first if it does not exist.
    """
    cards_out_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [_round_card(card) for card in cards]
    with cards_out_path.open("w", encoding="utf-8", newline="") as handle:
        json.dump(serializable, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_leads(leads, cards: list[dict], leads_out_dir: Path) -> None:
    """Write one sendable-lead CSV per Cell (Requirements 6.3, 6.4).

    Creates the Leads_Dir first if it does not exist. For each Cell a file
    ``<promo_id>_<segment_slug>.csv`` is written with columns ``client_id``,
    ``best_channel``, ``p_join``, ``control``, one row per Sendable_Lead (not
    excluded and ``control == 0``), ``control`` always 0. Control and Excluded
    Leads are never written. One file is written per Card so that every Cell --
    including those with zero Sendable_Leads -- has a (possibly header-only)
    lead file.
    """
    leads_out_dir.mkdir(parents=True, exist_ok=True)

    sendable = leads[(~leads["excluded"]) & (leads["control"] == 0)]
    for card in cards:
        promo_id = card["promo_id"]
        segment = card["segment"]
        cell_rows = sendable[
            (sendable["promo_id"] == promo_id) & (sendable["segment"] == segment)
        ]
        filename = f"{promo_id}_{_segment_slug(segment)}.csv"
        path = leads_out_dir / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_LEADS_COLUMNS)
            for row in cell_rows.itertuples(index=False):
                writer.writerow(
                    [row.client_id, row.best_channel, row.p_join, 0]
                )


def _print_summary(cards: list[dict]) -> None:
    """Print one summary line per Card (Requirement 6.5).

    Each line carries ``promo_id``, ``segment``, ``n_clients``,
    ``sendable_count``, ``expected_joiners``, ``expected_value``, and
    ``action``, tab-separated and in that order.
    """
    for card in cards:
        fields = [
            str(card["promo_id"]),
            str(card["segment"]),
            str(card["n_clients"]),
            str(card["sendable_count"]),
            str(round(float(card["expected_joiners"]), 2)),
            str(round(float(card["expected_value"]), 2)),
            str(card["action"]),
        ]
        print("\t".join(fields))


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end pipeline and return a process exit code.

    Parses ``argv`` (``None`` reads ``sys.argv[1:]``) into a :class:`Config`,
    then runs the pipeline in order (Requirement 6.1):

    1. ``loader.load`` -- load and validate the seven inputs.
    2. ``classify.classify`` -- per-Lead exclusion, best_channel, and control.
    3. ``build_cards_from_classified`` -- build one Card per Cell.

    Only after all three complete without error does the Reporter write
    ``outputs/cards.json`` (Requirement 6.2), the per-Cell sendable-lead CSVs
    (Requirements 6.3, 6.4), and print the summary table (Requirement 6.5).

    The loader is the only gate: any error here propagates out of :func:`main`
    before any output directory or file is created and before anything is
    printed (Requirement 6.6). A successful run returns 0.
    """
    cfg = _parse_config(argv)

    # The loader is the only gate: any error here propagates out of main before
    # any output directory or file is created and before anything is printed
    # (Requirement 6.6).
    frames = loader.load(cfg)

    leads = classify(frames, cfg)
    cards = build_cards_from_classified(leads, frames)

    _write_cards(cards, cfg.cards_out_path)
    _write_leads(leads, cards, cfg.leads_out_dir)
    _print_summary(cards)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
