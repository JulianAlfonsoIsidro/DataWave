"""Lead_Loader for the Part1_Optin_Pipeline.

Loads the Promo_Leads_File and selects the training population: the treated
P001/P002/P003 leads with a known opt-in outcome. This is the first halt gate
of the pipeline -- a missing file or an empty selection stops the run before any
downstream work or output (Requirements 1.7, 1.8).

The loader mirrors ``part2_network`` conventions: it reads with ``pd.read_csv``
and coerces ``control_group``/``joined`` via ``pd.to_numeric(errors="coerce")``
so quoted or oddly typed CSV values compare reliably against the integer
constants, with unparseable values becoming ``NaN`` that simply fail the
equality tests downstream rather than raising (Requirement 1.2, 1.6).

Ordered selection (Requirement 1):

1. existence check naming the missing path (1.7),
2. read + numeric coercion (1.2, 1.6),
3. keep ``control_group == TREATED_CONTROL_GROUP`` (1.2),
4. keep ``promo_id in PROMO_IDS`` (1.3),
5. set ``Join_Label = joined`` (1.5),
6. drop rows whose ``joined`` is NaN or not in ``{0, 1}`` (1.6),
7. dedup on ``(promo_id, client_id)`` keeping the first (1.4),
8. zero-lead guard raising when the result is empty (1.8).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from part1_optin.config import Config, PROMO_IDS, TREATED_CONTROL_GROUP


class Lead_Loader:
    """Load and select the treated-lead training population (Requirement 1)."""

    def __init__(self, config: Config) -> None:
        """Store the pipeline configuration.

        Args:
            config: The pipeline :class:`Config` carrying the
                ``promo_leads_path`` the loader reads from.
        """
        self.config = config

    def load(self) -> pd.DataFrame:
        """Load the Promo_Leads_File and return the treated-lead population.

        Returns the training population frame carrying the original lead columns
        plus a ``Join_Label`` column, filtered to treated P001/P002/P003 leads
        with a valid 0/1 ``joined`` outcome and deduplicated on
        ``(promo_id, client_id)``.

        Returns:
            The treated-lead frame with an added integer ``Join_Label`` column.

        Raises:
            FileNotFoundError: If ``promo_leads_path`` does not exist. The error
                names the missing path and the run halts before any downstream
                work (Requirement 1.7).
            ValueError: If zero treated leads remain after filtering. The run
                halts before any output (Requirement 1.8).
        """
        path = Path(self.config.promo_leads_path)

        # 1. Existence -- halt before any downstream work (Requirement 1.7).
        if not path.exists():
            raise FileNotFoundError(
                f"Promo_Leads_File not found at {path}"
            )

        # 2. Read + numeric coercion so typed/quoted values compare reliably;
        #    unparseable values become NaN and fail the equality tests below
        #    rather than raising (Requirements 1.2, 1.6).
        leads = pd.read_csv(path)
        leads["control_group"] = pd.to_numeric(
            leads["control_group"], errors="coerce"
        )
        leads["joined"] = pd.to_numeric(leads["joined"], errors="coerce")

        # 3. Keep only the Treated_Leads (control_group == 0) (Requirement 1.2).
        leads = leads[leads["control_group"] == TREATED_CONTROL_GROUP]

        # 4. Keep only P001/P002/P003 (Requirement 1.3).
        leads = leads[leads["promo_id"].isin(PROMO_IDS)]

        # 5. Label: Join_Label mirrors the joined column (Requirement 1.5).
        leads = leads.copy()
        leads["Join_Label"] = leads["joined"]

        # 6. Drop rows whose joined is NaN or not exactly 0/1 (Requirement 1.6).
        leads = leads[leads["Join_Label"].isin([0, 1])]
        leads["Join_Label"] = leads["Join_Label"].astype(int)

        # 7. Dedup on (promo_id, client_id), keeping the first (Requirement 1.4).
        leads = leads.drop_duplicates(
            subset=["promo_id", "client_id"], keep="first"
        )

        # 8. Zero-lead guard -- halt before any output (Requirement 1.8).
        if leads.empty:
            raise ValueError(
                "No treated leads found: zero P001/P002/P003 treated leads "
                "with a valid 0/1 'joined' outcome remain after filtering."
            )

        return leads.reset_index(drop=True)
