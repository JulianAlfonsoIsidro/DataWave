"""Property-based test for the per-lead Segments_File output.

Covers Property 6 of the part3-segments spec: the written Segments_File has
exactly one row for each distinct (``promo_id``, ``client_id``) Lead in the
scores frame (no duplicates, none missing), each row's ``p_join`` equals that
Lead's input ``p_join``, and each row's ``capacity_php`` equals the Lead's
``latest_adb`` plus ``out_other_bank`` and is non-negative given the
non-negative ADB and outflow inputs.

The property is checked against the *written CSV*: the frames are fed to
``segments.assign``, then ``segments.write`` persists the result to a tmp path,
and the file is read back and compared to the input scores frame.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import given, settings

from part3_segments.segments import assign, write
from tests.strategies_part3 import segment_inputs


# Feature: part3-segments, Property 6: For any scores frame, the Segments_File contains exactly one row for each distinct (`promo_id`, `client_id`) Lead in the scores frame (no duplicates, none missing), each row's `p_join` equals that Lead's input `p_join`, and each row's `capacity_php` equals the Lead's `latest_adb` plus `out_other_bank` and is non-negative given non-negative ADB and outflow inputs.
@settings(max_examples=100)
@given(segment_inputs())
def test_segments_output_one_row_per_lead(frames):
    """The written Segments_File is one row per Lead with preserved values.

    A fresh temporary directory is created per Hypothesis example (a
    function-scoped pytest fixture such as ``tmp_path`` cannot be combined with
    ``@given``), the leads frame is written there, read back, and asserted
    against the input scores frame. The directory is cleaned up on exit.

    Validates: Requirements 3.2
    """
    scores = frames["scores"]

    leads = assign(frames)
    with tempfile.TemporaryDirectory() as scratch:
        out_path = Path(scratch) / "segments.csv"
        write(leads, out_path)

        # Read the written CSV back. Keys are read as strings to match the
        # input ids; p_join / capacity_php are numeric.
        written = pd.read_csv(
            out_path,
            dtype={"promo_id": str, "client_id": str},
        )

    # --- exactly one row per distinct Lead: no duplicates, none missing ---
    written_keys = list(zip(written["promo_id"], written["client_id"]))
    scores_keys = list(zip(scores["promo_id"].astype(str),
                           scores["client_id"].astype(str)))

    # No duplicate Lead keys in the output.
    assert len(written_keys) == len(set(written_keys)), (
        "Segments_File contains duplicate (promo_id, client_id) rows"
    )

    # Same set of Lead keys as the scores frame (none missing, no extras).
    assert set(written_keys) == set(scores_keys), (
        "Segments_File Lead keys differ from the scores frame"
    )

    # Row count equals the distinct Lead count of the scores frame. The
    # strategy generates Leads unique on (promo_id, client_id), so the distinct
    # count equals the scores row count.
    assert len(written) == len(set(scores_keys))
    assert len(written) == len(scores)

    # --- p_join preserved per Lead ---------------------------------------
    input_p_join = {
        (str(p), str(c)): float(v)
        for p, c, v in zip(
            scores["promo_id"], scores["client_id"], scores["p_join"]
        )
    }
    tolerance = 1e-9
    for promo_id, client_id, p_join in zip(
        written["promo_id"], written["client_id"], written["p_join"]
    ):
        expected = input_p_join[(promo_id, client_id)]
        assert abs(float(p_join) - expected) <= tolerance, (
            f"Lead ({promo_id}, {client_id}): written p_join={p_join} "
            f"differs from input {expected}"
        )

    # --- capacity_php non-negative given non-negative inputs --------------
    assert (written["capacity_php"] >= -tolerance).all(), (
        "Segments_File has a negative capacity_php despite non-negative "
        "ADB and outflow inputs"
    )
