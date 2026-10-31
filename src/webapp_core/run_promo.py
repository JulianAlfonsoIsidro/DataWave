"""Promo-run orchestration for the Part 5 webapp.

This module wires the already-built Part 1/3/4 APIs into a single in-memory
RUN for the NEW PROMO and WHAT-IF flows (Requirements 3.3, 3.4, 3.5, 6.2). It
adds no modelling: it selects the eligible audience, scores it with the fitted
Part 1 model via :func:`part1_optin.scoring.score_promo`, assigns the four
Part 3 segment labels with :func:`part3_segments.segments.assign_segments`, and
builds the per-Cell cards with :func:`part4_cards.cards.build_cards`, then
derives the per-segment Sendable_Leads using the exact Part 4 "sendable"
definition (a Lead that is neither excluded nor held out as control).

Two dataclasses describe a run:

- :class:`PromoSpec` -- the immutable promo description built from the NEW
  PROMO form; :meth:`PromoSpec.to_promo_dict` produces the *flat* promo dict
  ``score_promo`` and ``assign_segments`` consume.
- :class:`RunResult` -- the in-memory result held in Streamlit session state,
  carrying the scored frame, the Segments_File-shaped frame, the cards, and the
  Sendable_Leads keyed by Segment_Label.

The ``data`` argument to :func:`run_promo` is a bundle of the loaded ``data/``
frames. It must carry:

- ``"customer_dna"`` -- the Customer_DNA frame (``client_id``, ``segment``,
  plus the reachability flags Part 4 reads), used by
  :func:`~webapp_core.audience.select_eligible_clients` and the Part 4 sendable
  classification.
- ``"adb_monthly"`` -- the ADB_Monthly frame (``client_id``, ``month``,
  ``adb_php``), used for the eligibility ADB floor and the Part 3 capacity.
- ``"features"`` -- the Part 2 feature frame (``client_id``, ``out_other_bank``,
  ...), used by the Part 3 capacity computation.

The empty-audience contract (Requirement 3.4): when no client satisfies the
eligibility filters, :func:`run_promo` returns a :class:`RunResult` with empty
``scored`` / ``segments_df`` frames, ``cards == []`` and an empty
``sendable_by_segment`` rather than raising, so the UI shows its empty-audience
message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from part1_optin.scoring import SCORE_PROMO_COLUMNS, score_promo
from part3_segments.segments import SEGMENTS_FILE_COLUMNS, assign_segments
from part4_cards.cards import build_cards
from part4_cards.classify import classify
from part4_cards.config import Config as CardsConfig
from part4_cards import loader as cards_loader


@dataclass(frozen=True)
class PromoSpec:
    """The immutable description of a promo to run (Requirement 3.1).

    Carries the attributes captured by the NEW PROMO form. ``promo_id`` is the
    auto-generated ``NEW-###`` id; ``eligible_segments`` are Customer_DNA
    segments (distinct from the four Part 3 Segment_Labels); ``channels`` are
    the promo's Allowed_Channels.
    """

    promo_id: str
    product_type: str
    mechanic: str
    threshold_php: float
    reward: str
    eligible_segments: list[str]
    min_adb: float
    channels: list[str]

    def to_promo_dict(self) -> dict:
        """The *flat* promo dict ``score_promo`` and ``assign_segments`` expect.

        ``score_promo`` reads ``promo_id``, ``mechanic``, and ``threshold_php``;
        ``assign_segments`` reads ``promo_id`` and ``threshold_php``. The extra
        ``product_type``, ``reward``, and ``channels`` keys are carried along so
        a single flat dict describes the promo everywhere a flat shape is
        wanted. The dict-of-dicts shape ``build_cards`` wants is produced
        separately by :func:`_cards_promo_dict`.
        """
        return {
            "promo_id": self.promo_id,
            "mechanic": self.mechanic,
            "threshold_php": self.threshold_php,
            "product_type": self.product_type,
            "reward": self.reward,
            "channels": list(self.channels),
        }


@dataclass
class RunResult:
    """The in-memory result of one promo RUN (Requirement 3.5).

    Held in Streamlit session state so the RESULTS, DOWNLOAD LEADS, and WHAT-IF
    surfaces all operate on the same run. ``scored`` is one row per eligible
    client (``client_id``, ``p_join``, ``top_driver_1..3``); ``segments_df`` is
    Segments_File-shaped (the eight :data:`SEGMENTS_FILE_COLUMNS`); ``cards`` is
    one dict per Cell from :func:`build_cards`; ``sendable_by_segment`` maps
    each Segment_Label to a frame of that segment's Sendable_Leads.
    """

    promo_spec: PromoSpec
    scored: pd.DataFrame
    segments_df: pd.DataFrame
    cards: list[dict]
    sendable_by_segment: dict[str, pd.DataFrame] = field(default_factory=dict)


def _cards_promo_dict(promo_spec: PromoSpec) -> dict[str, dict]:
    """The dict-of-dicts ``build_cards`` expects: ``promo_id -> {...}``.

    ``build_cards`` synthesizes a ``promo_history`` frame from a mapping of
    ``promo_id`` to a per-promo dict carrying at least ``channels`` (the
    Allowed_Channels) and ``mechanic`` (for the action rule). This is a
    different shape from the flat dict :meth:`PromoSpec.to_promo_dict` returns,
    so it is built explicitly here.
    """
    return {
        promo_spec.promo_id: {
            "mechanic": promo_spec.mechanic,
            "channels": list(promo_spec.channels),
        }
    }


def _empty_result(promo_spec: PromoSpec) -> RunResult:
    """An empty :class:`RunResult` for an all-filtered-out audience.

    Returns empty ``scored`` and ``segments_df`` frames carrying their correct
    column schemas, ``cards == []`` and an empty ``sendable_by_segment`` so the
    UI shows the empty-audience message without erroring (Requirement 3.4).
    """
    return RunResult(
        promo_spec=promo_spec,
        scored=pd.DataFrame(columns=SCORE_PROMO_COLUMNS),
        segments_df=pd.DataFrame(columns=SEGMENTS_FILE_COLUMNS),
        cards=[],
        sendable_by_segment={},
    )


def _sendable_by_segment(
    segments_df: pd.DataFrame, promo_spec: PromoSpec
) -> dict[str, pd.DataFrame]:
    """Derive each segment's Sendable_Leads using the Part 4 sendable rule.

    Sendable is Part 4's definition: a Lead that is neither excluded nor held
    out as control (``~excluded & control == 0``). This reuses the exact Part 4
    classifier over the same reference frames ``build_cards`` loads, with a
    ``promo_history`` synthesized from the promo so the channel gating and
    control split match the cards, then groups the sendable rows by
    Segment_Label. The returned frames back DOWNLOAD LEADS (Requirement 4.3)
    and the PAST-PROMOS-style sendable set (Requirement 5.2).
    """
    cfg = CardsConfig()
    frames = cards_loader.load(cfg)

    # Synthesize the one-row-per-promo promo_history the classifier reads for
    # Allowed_Channels gating, exactly as build_cards does (comma-joined
    # channels string + mechanic), and attach the in-memory segments frame.
    promo_rows = [
        {
            "promo_id": promo_spec.promo_id,
            "channels": ", ".join(promo_spec.channels or []),
            "mechanic": promo_spec.mechanic,
        }
    ]
    frames = {
        **frames,
        "segments": segments_df,
        "promo_history": pd.DataFrame(
            promo_rows, columns=["promo_id", "channels", "mechanic"]
        ),
    }

    leads = classify(frames, cfg)
    sendable = leads[(~leads["excluded"]) & (leads["control"] == 0)]

    by_segment: dict[str, pd.DataFrame] = {}
    for segment, cell in sendable.groupby("segment", sort=False):
        by_segment[str(segment)] = cell.reset_index(drop=True)
    return by_segment


def run_promo(
    promo_spec: PromoSpec,
    model: Any,
    config: Any,
    data: dict[str, pd.DataFrame],
) -> RunResult:
    """Run a promo end to end and return its :class:`RunResult`.

    Orchestrates the RUN pipeline (Requirement 3.3): select the eligible
    audience, score it with the fitted model, assign the four Part 3 segment
    labels, build the per-Cell cards, and derive the per-segment
    Sendable_Leads. The model is reused as-is -- never retrained or
    recalibrated -- so WHAT-IF can call this again with only ``threshold_php``
    changed (Requirement 6.2).

    Args:
        promo_spec: The promo to run.
        model: The fitted :class:`~part1_optin.model.Calibrated_Model` reloaded
            from ``outputs/``; passed straight to ``score_promo``.
        config: The Part 1 pipeline ``Config`` ``score_promo`` reads its client
            source paths from.
        data: The loaded ``data/`` frames bundle. Must carry ``customer_dna``,
            ``adb_monthly``, and ``features`` (see module docstring).

    Returns:
        A :class:`RunResult`. For an all-filtered-out audience it is the empty
        result from :func:`_empty_result` (Requirement 3.4).
    """
    # Local import avoids a module-level cycle and keeps audience selection with
    # the other pure webapp_core logic.
    from webapp_core.audience import select_eligible_clients

    promo_dict = promo_spec.to_promo_dict()

    # 1. Select the eligible audience from the raw data/ frames (Requirement 3.2).
    clients_df = select_eligible_clients(
        data["customer_dna"],
        data["adb_monthly"],
        promo_spec.eligible_segments,
        promo_spec.min_adb,
    )

    # Empty audience: return the empty RunResult, do not score/segment/card
    # (Requirement 3.4).
    if clients_df.empty:
        return _empty_result(promo_spec)

    # 2. Score the eligible clients with the fitted model (Requirement 3.3).
    scored = score_promo(promo_dict, clients_df, model, config)

    # 3. Assign the four Part 3 segment labels from score vs capacity. The
    # capacity computation reads the ADB and Part 2 feature frames.
    segment_frames = {
        "adb": data["adb_monthly"],
        "features": data["features"],
    }
    segments_df = assign_segments(scored, promo_dict, segment_frames)

    # 4. Build one card per Cell (Requirement 3.3). build_cards wants the
    # dict-of-dicts promo shape, not the flat one score_promo consumed.
    cards = build_cards(segments_df, _cards_promo_dict(promo_spec))

    # 5. Derive the per-segment Sendable_Leads using Part 4's sendable rule so
    # DOWNLOAD LEADS and the predicted/actual comparison share one definition.
    sendable_by_segment = _sendable_by_segment(segments_df, promo_spec)

    return RunResult(
        promo_spec=promo_spec,
        scored=scored,
        segments_df=segments_df,
        cards=cards,
        sendable_by_segment=sendable_by_segment,
    )
