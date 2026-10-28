"""Feature_Assembler and FeatureSchema for the Part1_Optin_Pipeline.

The Feature_Assembler turns treated leads into one Feature_Row per lead by
joining several approved client and promo data sources (Requirement 2), and
owns the fitted ``FeatureSchema`` that is the contract between training and
scoring.

This module holds the shared scaffolding every feature block builds on:

- the ``FeatureSchema`` dataclass (the ordered column list, the categorical
  ``value -> code`` maps, the discovered product-type columns, and the part2
  column list) plus its ``to_dict`` / ``from_dict`` sidecar persistence,
- the ``Feature_Assembler.__init__`` / ``fit_transform`` / ``transform``
  surface (the feature blocks themselves land in later tasks 4.x and 5.x), and
- the answer-key guard that asserts no path the assembler is about to open
  contains ``ANSWER_KEY_MARKER``, turning Requirement 2.14 into a runtime
  invariant.

The design mirrors ``part2_network`` conventions: absolute imports
(``from part1_optin...``), module-level helpers, and ``Config`` as the single
source of input paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from part1_optin.config import (
    ANSWER_KEY_MARKER,
    Config,
    DNA_CATEGORICAL_COLUMNS,
    DNA_NUMERIC_COLUMNS,
    PROMO_MECHANIC_COLUMN,
)

# Name of the engineered flag marking a lead whose client_id is absent from the
# Customer_DNA_File (Requirement 2.2).
CUSTOMER_DNA_MISSING_FLAG = "Customer_DNA_Missing_Flag"

# Prefix for the per-product_type Active_Product_Count columns (Requirement 2.3).
# A distinct product_type ``t`` discovered at fit time yields the column
# ``active_count_<t>``.
ACTIVE_COUNT_PREFIX = "active_count_"

# Product_Ownership_File ``status`` value that counts toward an
# Active_Product_Count (Requirement 2.3).
ACTIVE_STATUS = "Active"

# Name of the column holding the client's chronologically latest ``adb_php``
# (Requirement 2.5).
LATEST_ADB_COLUMN = "latest_adb"

# Name of the column holding the least-squares slope of ``adb_php`` over the
# client's most recent up-to-three months (Requirements 2.5, 2.6).
ADB_TREND_COLUMN = "adb_trend"

# Name of the engineered flag marking a lead whose client_id is absent from the
# ADB_File (Requirement 2.7).
ADB_MISSING_FLAG = "ADB_Missing_Flag"

# Number of most-recent months the ADB_Trend slope is fit over (Requirement 2.5).
ADB_TREND_WINDOW = 3

# Name of the column holding a client's average number of Contact_History_File
# rows per distinct calendar month (Requirements 2.8, 2.9).
AVG_CONTACTS_PER_MONTH_COLUMN = "avg_contacts_per_month"

# Length of the ``YYYY-MM`` month prefix derived from a ``YYYY-MM-DD``
# ``contact_date`` to count distinct calendar months (Requirement 2.8).
CONTACT_MONTH_PREFIX_LENGTH = 7

# Name of the column holding a client's NDB membership flag (Requirement 2.10).
NDB_FLAG_COLUMN = "ndb_flag"

# Name of the engineered flag marking a lead whose client_id is absent from the
# Part2_Features_File (Requirement 2.12).
PART2_FEATURES_MISSING_FLAG = "Part2_Features_Missing_Flag"

# Name of the column holding the joined promo's ``threshold_php``, passed through
# numerically (Requirement 2.13).
PROMO_THRESHOLD_COLUMN = "threshold_php"


@dataclass
class FeatureSchema:
    """The fitted feature contract reapplied identically at score time.

    A ``fit_transform`` call *learns* this schema and a ``transform`` call
    *reapplies* a frozen copy, so the column set, column order, and categorical
    encoding of a scoring matrix match the trained matrix exactly (Requirements
    2.1, 7.2). The schema is also persisted to the model sidecar via
    :meth:`to_dict` / :meth:`from_dict` for out-of-process reuse (Requirement
    6.1).

    Fields:

    - ``columns``: the ordered final column list -- the authoritative schema
      ``transform`` reindexes onto.
    - ``categorical_maps``: ``{column: {category_value: code}}`` for each DNA
      categorical column and ``mechanic``; code ``0`` is reserved for
      missing/unseen values.
    - ``product_type_columns``: one ``active_count_<product_type>`` column per
      distinct ``product_type`` discovered at fit time.
    - ``part2_columns``: the Part2_Features_File column names joined in.
    """

    columns: list[str] = field(default_factory=list)
    categorical_maps: dict[str, dict] = field(default_factory=dict)
    product_type_columns: list[str] = field(default_factory=list)
    part2_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of this schema for the sidecar.

        Round-trips with :meth:`from_dict`. The field names are preserved
        verbatim so the sidecar document is self-describing; the nested
        ``categorical_maps`` values are plain dicts and so serialize directly.
        """
        return {
            "columns": list(self.columns),
            "categorical_maps": {
                column: dict(mapping)
                for column, mapping in self.categorical_maps.items()
            },
            "product_type_columns": list(self.product_type_columns),
            "part2_columns": list(self.part2_columns),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeatureSchema":
        """Rebuild a ``FeatureSchema`` from a :meth:`to_dict` document.

        Missing keys fall back to empty collections so a partial or legacy
        sidecar still yields a usable (if empty) schema rather than raising.
        """
        return cls(
            columns=list(d.get("columns", [])),
            categorical_maps={
                column: dict(mapping)
                for column, mapping in d.get("categorical_maps", {}).items()
            },
            product_type_columns=list(d.get("product_type_columns", [])),
            part2_columns=list(d.get("part2_columns", [])),
        )


def _least_squares_slope(xs, ys) -> float:
    """Return the ordinary least-squares slope of ``ys`` regressed on ``xs``.

    Computes the closed-form slope
    ``sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean) ** 2)`` -- identical to
    ``numpy.polyfit(xs, ys, 1)[0]`` -- without a numpy dependency so the ADB
    block (Requirements 2.5, 2.6) stays deterministic and dependency-light.

    ``xs`` is the ascending month index ``0, 1, 2, ...`` and ``ys`` the matching
    ``adb_php`` values. The caller guarantees at least two points, so the
    denominator (the variance of the distinct ascending indices) is non-zero;
    a degenerate zero denominator still returns ``0.0`` rather than dividing by
    zero.
    """
    xs = [float(x) for x in xs]
    ys = [float(y) for y in ys]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def assert_not_answer_key(path) -> Path:
    """Assert ``path`` is not a forbidden Answer_Key_File, returning it.

    Turns the answer-key prohibition (Requirement 2.14) into a runtime
    invariant: every path the Feature_Assembler is about to open is routed
    through this guard, which raises ``ValueError`` if the path's string form
    contains :data:`ANSWER_KEY_MARKER` (``"_answer_key"``). The path is returned
    unchanged on success so call sites can wrap a read inline, e.g.
    ``pd.read_csv(assert_not_answer_key(config.customer_dna_path))``.

    ``path`` may be a :class:`~pathlib.Path` or ``str``; it is coerced to
    ``Path`` and compared on its string representation so the marker is caught
    anywhere in the path, not only the final name component.
    """
    path = Path(path)
    if ANSWER_KEY_MARKER in str(path):
        raise ValueError(
            f"refusing to open forbidden answer-key path {path!r}: "
            f"paths containing {ANSWER_KEY_MARKER!r} are prohibited "
            f"(Requirement 2.14)"
        )
    return path


class Feature_Assembler:
    """Build one Feature_Row per treated lead from the approved sources.

    Split into a **fit** phase (:meth:`fit_transform`) that learns the
    ``FeatureSchema`` and a **transform** phase (:meth:`transform`) that
    reapplies a frozen schema, so scoring never re-derives columns from its own
    data (Requirements 2.1, 7.2). The assembler reads only the eight approved
    ``Config`` source paths and routes every one through
    :func:`assert_not_answer_key` so no ``_answer_key`` file is ever opened
    (Requirement 2.14).
    """

    def __init__(self, config: Config) -> None:
        """Store the ``Config`` holding the approved input paths.

        No source files are read here; reads happen in :meth:`fit_transform` /
        :meth:`transform`, each guarded by :func:`assert_not_answer_key`.
        """
        self.config = config

    def _read_customer_dna(self) -> pd.DataFrame:
        """Read the Customer_DNA_File through the answer-key guard.

        Routes :attr:`Config.customer_dna_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the DNA source read. Returns the raw frame; the DNA block does all
        selection and encoding.
        """
        return pd.read_csv(assert_not_answer_key(self.config.customer_dna_path))

    def _customer_dna_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the Customer_DNA feature block for ``leads`` (Requirements 2.1, 2.2).

        Produces one row per lead, indexed to match ``leads.index``, with:

        - the pass-through numeric predictors in :data:`DNA_NUMERIC_COLUMNS`,
        - an ordinal-encoded code column per categorical in
          :data:`DNA_CATEGORICAL_COLUMNS`, encoded through a deterministic
          ``value -> code`` map (code ``0`` reserved for missing/unseen), and
        - the :data:`CUSTOMER_DNA_MISSING_FLAG` column, ``1`` for a lead whose
          ``client_id`` is absent from the Customer_DNA_File and ``0`` otherwise.

        Determinism and the fit/transform contract (Requirements 2.1, 7.2):

        - When ``fit`` is ``True`` the categorical ``value -> code`` maps are
          *learned* from the sorted distinct non-null fit-time values of each
          categorical column and written into ``schema.categorical_maps``; codes
          run ``1..N`` in sorted order so the same category always maps to the
          same code on every run (``0`` stays reserved).
        - When ``fit`` is ``False`` the *frozen* maps already in
          ``schema.categorical_maps`` are reused, so a value unseen at fit time
          (or a client absent from the DNA file) encodes to the reserved ``0``.

        Missing-client handling (Requirement 2.2): leads are left-joined onto the
        DNA frame on ``client_id``; a lead with no match has every numeric
        predictor filled ``0``, every categorical code ``0`` (the reserved
        missing/unseen code), and ``Customer_DNA_Missing_Flag = 1``. Matched
        leads get flag ``0``.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema` whose ``categorical_maps`` are
                populated when ``fit`` is ``True`` and read when it is ``False``.
            fit: ``True`` to learn the categorical maps, ``False`` to reuse them.

        Returns:
            A frame indexed like ``leads`` with the numeric pass-throughs, the
            categorical code columns, and the missing flag.
        """
        dna = self._read_customer_dna()

        # Learn or reuse the deterministic value -> code maps for each
        # categorical column (Requirement 2.1). Codes run 1..N over the sorted
        # distinct non-null fit-time values; 0 stays reserved for missing/unseen.
        if fit:
            for column in DNA_CATEGORICAL_COLUMNS:
                distinct = sorted(dna[column].dropna().unique())
                schema.categorical_maps[column] = {
                    value: code for code, value in enumerate(distinct, start=1)
                }

        # Index the DNA frame by client_id so leads can look up their row; a
        # duplicated client_id in the source keeps the first occurrence so the
        # join stays one-to-one.
        dna_by_client = dna.drop_duplicates(subset="client_id", keep="first")
        dna_by_client = dna_by_client.set_index("client_id")
        present = leads["client_id"].isin(dna_by_client.index)

        block = pd.DataFrame(index=leads.index)

        # Numeric pass-throughs (Requirement 2.1): look each lead's value up by
        # client_id; absent clients become NaN -> filled 0 (Requirement 2.2).
        for column in DNA_NUMERIC_COLUMNS:
            values = leads["client_id"].map(dna_by_client[column])
            block[column] = pd.to_numeric(values, errors="coerce").fillna(0)

        # Categorical codes (Requirement 2.1): map each lead's raw category
        # value through the frozen value -> code map; missing clients and values
        # unseen at fit time fall through to the reserved 0 (Requirement 2.2).
        for column in DNA_CATEGORICAL_COLUMNS:
            code_map = schema.categorical_maps.get(column, {})
            raw = leads["client_id"].map(dna_by_client[column])
            block[column] = raw.map(code_map).fillna(0).astype(int)

        # Missing flag: 1 when the lead's client_id is absent from the DNA file,
        # else 0 (Requirement 2.2).
        block[CUSTOMER_DNA_MISSING_FLAG] = (~present).astype(int)

        return block

    def _read_product_ownership(self) -> pd.DataFrame:
        """Read the Product_Ownership_File through the answer-key guard.

        Routes :attr:`Config.product_ownership_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the product-ownership source read. Returns the raw frame; the
        active-product-count block does all selection and counting.
        """
        return pd.read_csv(
            assert_not_answer_key(self.config.product_ownership_path)
        )

    def _active_product_count_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the Active_Product_Count feature block (Requirements 2.3, 2.4).

        Produces one row per lead, indexed to match ``leads.index``, with one
        ``active_count_<product_type>`` column per distinct ``product_type``
        discovered in the Product_Ownership_File at fit time. Each cell holds the
        count of that lead's client rows whose ``status`` equals ``"Active"`` for
        that ``product_type`` (Requirement 2.3). A client/product pair with no
        matching Active row -- including a client absent from the file entirely --
        is ``0`` (Requirement 2.4).

        The fit/transform contract (Requirements 2.1, 7.2):

        - When ``fit`` is ``True`` the distinct ``product_type`` values are
          discovered from the file, sorted, and recorded as the sorted
          ``active_count_<product_type>`` column names in
          ``schema.product_type_columns``.
        - When ``fit`` is ``False`` the *frozen* ``schema.product_type_columns``
          is reused: counts are produced only for those columns, a product_type
          seen only at score time is dropped, and a fit-time product_type absent
          from the new data is zero-filled.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema` whose ``product_type_columns`` are
                populated when ``fit`` is ``True`` and read when ``False``.
            fit: ``True`` to discover the product-type columns, ``False`` to
                reuse them.

        Returns:
            A frame indexed like ``leads`` with the (integer) active-count
            columns named in ``schema.product_type_columns``, in that order.
        """
        ownership = self._read_product_ownership()

        # Discover (fit) or reuse (transform) the sorted active-count column
        # names, one per distinct product_type seen at fit time (Requirement
        # 2.3). Codes are the column names ``active_count_<product_type>``.
        if fit:
            distinct = sorted(ownership["product_type"].dropna().unique())
            schema.product_type_columns = [
                f"{ACTIVE_COUNT_PREFIX}{product_type}" for product_type in distinct
            ]

        # Count each client's Active rows per product_type. Restrict to Active
        # status first (Requirement 2.3), then group by (client_id,
        # product_type) and size; a client/product pair with no Active rows
        # simply never appears here and resolves to 0 below (Requirement 2.4).
        active = ownership[ownership["status"] == ACTIVE_STATUS]
        counts = (
            active.groupby(["client_id", "product_type"]).size().unstack(fill_value=0)
        )

        block = pd.DataFrame(index=leads.index)

        # Emit exactly the frozen fit-time columns in order. For each, map every
        # lead's client_id onto its Active count for that product_type; absent
        # clients and fit-time product_types missing from the new data fall
        # through to 0 (Requirement 2.4).
        for column in schema.product_type_columns:
            product_type = column[len(ACTIVE_COUNT_PREFIX):]
            if product_type in counts.columns:
                values = leads["client_id"].map(counts[product_type])
            else:
                values = pd.Series(index=leads.index, dtype="float64")
            block[column] = values.fillna(0).astype(int)

        return block

    def _read_adb(self) -> pd.DataFrame:
        """Read the ADB_File through the answer-key guard.

        Routes :attr:`Config.adb_monthly_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the ADB source read. Returns the raw frame; the ADB block does all
        selection, ordering, and slope computation.
        """
        return pd.read_csv(assert_not_answer_key(self.config.adb_monthly_path))

    def _adb_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the ADB feature block for ``leads`` (Requirements 2.5, 2.6, 2.7).

        Produces one row per lead, indexed to match ``leads.index``, with:

        - :data:`LATEST_ADB_COLUMN` -- the ``adb_php`` at the client's
          chronologically most recent ``month`` (Requirement 2.5),
        - :data:`ADB_TREND_COLUMN` -- the least-squares regression slope of
          ``adb_php`` against an ascending month index ``0, 1, 2, ...`` over the
          client's most recent up-to-:data:`ADB_TREND_WINDOW` months; a client
          with a single month of data gets slope ``0`` (Requirements 2.5, 2.6),
          and
        - :data:`ADB_MISSING_FLAG` -- ``1`` for a lead whose ``client_id`` is
          absent from the ADB_File and ``0`` otherwise (Requirement 2.7).

        Missing-client handling (Requirement 2.7): a lead whose ``client_id``
        never appears in the ADB_File has both ``latest_adb`` and ``adb_trend``
        set to ``0`` and ``ADB_Missing_Flag = 1``; present clients get flag ``0``.

        The ADB block learns nothing at fit time -- its three columns are fixed
        and carry no categorical map or discovered column set -- so ``schema``
        and ``fit`` are accepted only to mirror the block signatures and are
        otherwise unused.

        ``month`` values are ``YYYY-MM`` strings that sort chronologically under
        plain lexicographic ordering, so "most recent" is the lexicographic
        maximum and the trailing window is the last rows after a string sort.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema`; unused by this block.
            fit: Unused by this block (no fit-time state to learn).

        Returns:
            A frame indexed like ``leads`` with ``latest_adb``, ``adb_trend``,
            and ``ADB_Missing_Flag``.
        """
        adb = self._read_adb()

        # Coerce adb_php to numeric so a stray non-numeric value does not derail
        # the slope arithmetic; month stays a string and sorts chronologically
        # under plain lexicographic ordering (YYYY-MM).
        adb = adb.copy()
        adb["adb_php"] = pd.to_numeric(adb["adb_php"], errors="coerce")

        # Compute latest_adb and adb_trend once per client that appears in the
        # file, keyed by client_id, then map onto leads below.
        latest_by_client: dict = {}
        trend_by_client: dict = {}
        for client_id, group in adb.groupby("client_id"):
            # Chronological order: YYYY-MM strings sort chronologically, so a
            # plain ascending sort puts the most recent month last.
            ordered = group.sort_values("month")
            values = ordered["adb_php"].to_numpy(dtype="float64")

            # Latest_ADB: the adb_php at the client's most recent month
            # (Requirement 2.5).
            latest_by_client[client_id] = values[-1]

            # ADB_Trend: least-squares slope of adb_php vs ascending month index
            # (0, 1, 2, ...) over the last up-to-3 months. A single month -> 0
            # (Requirement 2.6); there is no unique line through one point.
            window = values[-ADB_TREND_WINDOW:]
            if len(window) < 2:
                trend_by_client[client_id] = 0.0
            else:
                x = range(len(window))
                # Least-squares slope of adb_php vs the ascending index, equal
                # to numpy.polyfit(x, y, 1)[0], computed closed-form so the
                # block stays dependency-light and deterministic.
                trend_by_client[client_id] = _least_squares_slope(x, window)

        block = pd.DataFrame(index=leads.index)

        present = leads["client_id"].isin(latest_by_client)

        # Map each lead's client_id onto its precomputed latest/trend; an absent
        # client becomes NaN -> filled 0 (Requirement 2.7).
        latest = leads["client_id"].map(latest_by_client)
        trend = leads["client_id"].map(trend_by_client)
        block[LATEST_ADB_COLUMN] = latest.fillna(0.0).astype(float)
        block[ADB_TREND_COLUMN] = trend.fillna(0.0).astype(float)

        # Missing flag: 1 when the lead's client_id is absent from the ADB_File,
        # else 0 (Requirement 2.7).
        block[ADB_MISSING_FLAG] = (~present).astype(int)

        return block

    def _read_contact_history(self) -> pd.DataFrame:
        """Read the Contact_History_File through the answer-key guard.

        Routes :attr:`Config.contact_history_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the contact-history source read. Returns the raw frame; the
        contact-history block does all month derivation and counting.
        """
        return pd.read_csv(
            assert_not_answer_key(self.config.contact_history_path)
        )

    def _contact_history_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the Contact_History feature block (Requirements 2.8, 2.9).

        Produces one row per lead, indexed to match ``leads.index``, with the
        single :data:`AVG_CONTACTS_PER_MONTH_COLUMN` column. For each client,
        ``avg_contacts_per_month`` is the client's total count of
        Contact_History_File rows divided by the number of distinct calendar
        months in which that client has at least one contact row (Requirement
        2.8). A client with no contact rows -- including a client absent from
        the file entirely -- is ``0`` via a guarded division (Requirement 2.9).

        The distinct calendar month of a contact row is the ``YYYY-MM`` prefix
        of its ``contact_date`` (a ``YYYY-MM-DD`` string); the per-client divisor
        is the count of distinct such prefixes, so multiple contacts in the same
        month collapse to one month. Because the numerator (total rows) and the
        denominator (distinct months) are both counted from the same rows, the
        ratio is always well-defined whenever the client has at least one row.

        The contact-history block learns nothing at fit time -- its one column is
        fixed and carries no categorical map or discovered column set -- so
        ``schema`` and ``fit`` are accepted only to mirror the block signatures
        and are otherwise unused.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema`; unused by this block.
            fit: Unused by this block (no fit-time state to learn).

        Returns:
            A frame indexed like ``leads`` with ``avg_contacts_per_month``.
        """
        contacts = self._read_contact_history()

        # Derive the YYYY-MM calendar month from each contact_date (YYYY-MM-DD)
        # so distinct-month counting collapses same-month contacts (Requirement
        # 2.8). The prefix is taken on the string form to tolerate however the
        # date was parsed on read.
        contacts = contacts.copy()
        contacts["_contact_month"] = (
            contacts["contact_date"].astype(str).str[:CONTACT_MONTH_PREFIX_LENGTH]
        )

        grouped = contacts.groupby("client_id")
        # Total contact rows per client (the numerator, Requirement 2.8).
        total_rows = grouped.size()
        # Distinct calendar months per client (the divisor, Requirement 2.8);
        # same-month contacts count once.
        distinct_months = grouped["_contact_month"].nunique()

        # Guarded division per client: total rows / distinct months. The divisor
        # is the count of distinct months among the very rows being counted, so
        # it is >= 1 for any client present here; clients absent from the file
        # never appear and resolve to 0 below (Requirement 2.9).
        avg_by_client = (total_rows / distinct_months).where(distinct_months > 0, 0.0)

        block = pd.DataFrame(index=leads.index)

        # Map each lead's client_id onto its average; a client with no contact
        # rows (absent from avg_by_client) becomes NaN -> filled 0, the guarded
        # no-contacts case (Requirement 2.9).
        values = leads["client_id"].map(avg_by_client)
        block[AVG_CONTACTS_PER_MONTH_COLUMN] = values.fillna(0.0).astype(float)

        return block

    def _read_ndb(self) -> pd.DataFrame:
        """Read the NDB_File through the answer-key guard.

        Routes :attr:`Config.ndb_path` through :func:`assert_not_answer_key`
        before opening, so Requirement 2.14 holds for the NDB source read.
        Returns the raw frame; the NDB block does all membership testing.
        """
        return pd.read_csv(assert_not_answer_key(self.config.ndb_path))

    def _ndb_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the NDB feature block for ``leads`` (Requirement 2.10).

        Produces one row per lead, indexed to match ``leads.index``, with the
        single :data:`NDB_FLAG_COLUMN` column. ``ndb_flag`` is ``1`` for a lead
        whose ``client_id`` appears anywhere in the NDB_File and ``0`` otherwise
        (Requirement 2.10) -- a pure membership test, independent of the
        ``flag_type`` / ``flag_date`` columns and of how many NDB rows a client
        has.

        The NDB block learns nothing at fit time -- its one column is fixed and
        carries no categorical map or discovered column set -- so ``schema`` and
        ``fit`` are accepted only to mirror the block signatures and are
        otherwise unused.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema`; unused by this block.
            fit: Unused by this block (no fit-time state to learn).

        Returns:
            A frame indexed like ``leads`` with ``ndb_flag``.
        """
        ndb = self._read_ndb()

        # Membership set of every client_id that appears in the NDB_File. A
        # client's presence alone sets the flag, regardless of how many rows or
        # which flag_type it carries (Requirement 2.10).
        ndb_clients = set(ndb["client_id"])

        block = pd.DataFrame(index=leads.index)
        block[NDB_FLAG_COLUMN] = leads["client_id"].isin(ndb_clients).astype(int)

        return block

    def _read_part2_features(self) -> pd.DataFrame:
        """Read the Part2_Features_File through the answer-key guard.

        Routes :attr:`Config.features_part2_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the part2-features source read. Returns the raw frame; the part2
        block does all column discovery and joining.
        """
        return pd.read_csv(
            assert_not_answer_key(self.config.features_part2_path)
        )

    def _part2_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the Part2-join feature block (Requirements 2.11, 2.12).

        Produces one row per lead, indexed to match ``leads.index``, with:

        - one column per Part2_Features_File column (every column except
          ``client_id``), joined onto each lead by ``client_id`` (Requirement
          2.11), and
        - the :data:`PART2_FEATURES_MISSING_FLAG` column, ``1`` for a lead whose
          ``client_id`` is absent from the Part2_Features_File and ``0``
          otherwise (Requirement 2.12).

        The fit/transform contract (Requirements 2.1, 7.2):

        - When ``fit`` is ``True`` the part2 feature columns -- all
          Part2_Features_File columns except ``client_id``, in file order -- are
          discovered and recorded into ``schema.part2_columns``.
        - When ``fit`` is ``False`` the *frozen* ``schema.part2_columns`` is
          reused: a column present in the frozen schema but absent from the new
          data is zero-filled, and a column seen only at score time is dropped,
          so the emitted columns match the trained matrix exactly.

        Missing-client handling (Requirement 2.12): leads are left-joined onto
        the part2 frame on ``client_id``; a lead with no match has every part2
        feature column filled ``0`` and ``Part2_Features_Missing_Flag = 1``.
        Matched leads get flag ``0``.

        Args:
            leads: The treated-lead frame; must carry a ``client_id`` column.
            schema: The :class:`FeatureSchema` whose ``part2_columns`` are
                populated when ``fit`` is ``True`` and read when ``False``.
            fit: ``True`` to discover the part2 columns, ``False`` to reuse them.

        Returns:
            A frame indexed like ``leads`` with the part2 feature columns named
            in ``schema.part2_columns`` (in that order) and the missing flag.
        """
        part2 = self._read_part2_features()

        # Discover (fit) or reuse (transform) the part2 feature column names --
        # every Part2_Features_File column except the client_id join key, in
        # file order (Requirement 2.11).
        if fit:
            schema.part2_columns = [
                column for column in part2.columns if column != "client_id"
            ]

        # Index the part2 frame by client_id so leads can look up their row; a
        # duplicated client_id in the source keeps the first occurrence so the
        # join stays one-to-one.
        part2_by_client = part2.drop_duplicates(subset="client_id", keep="first")
        part2_by_client = part2_by_client.set_index("client_id")
        present = leads["client_id"].isin(part2_by_client.index)

        block = pd.DataFrame(index=leads.index)

        # Emit exactly the frozen fit-time part2 columns in order. For each, map
        # every lead's value by client_id; absent clients and fit-time columns
        # missing from the new data fall through to 0 (Requirements 2.11, 2.12).
        for column in schema.part2_columns:
            if column in part2_by_client.columns:
                values = leads["client_id"].map(part2_by_client[column])
            else:
                values = pd.Series(index=leads.index, dtype="float64")
            block[column] = pd.to_numeric(values, errors="coerce").fillna(0)

        # Missing flag: 1 when the lead's client_id is absent from the
        # Part2_Features_File, else 0 (Requirement 2.12).
        block[PART2_FEATURES_MISSING_FLAG] = (~present).astype(int)

        return block

    def _read_promo_history(self) -> pd.DataFrame:
        """Read the Promo_History_File through the answer-key guard.

        Routes :attr:`Config.promo_history_path` through
        :func:`assert_not_answer_key` before opening, so Requirement 2.14 holds
        for the promo-history source read. Returns the raw frame; the promo
        block does all selection and encoding.
        """
        return pd.read_csv(assert_not_answer_key(self.config.promo_history_path))

    def _promo_attributes_block(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build the Promo_Attributes feature block (Requirements 2.11, 2.13).

        Produces one row per lead, indexed to match ``leads.index``, with:

        - an ordinal-encoded :data:`PROMO_MECHANIC_COLUMN` (``mechanic``) code,
          encoded through a deterministic ``value -> code`` map (code ``0``
          reserved for missing/unseen) stored in ``schema.categorical_maps``
          under the mechanic column name, exactly like the DNA categoricals, and
        - the :data:`PROMO_THRESHOLD_COLUMN` (``threshold_php``) numeric
          pass-through.

        Both are joined onto each lead by ``promo_id`` from the
        Promo_History_File (Requirement 2.13).

        The fit/transform contract (Requirements 2.1, 7.2):

        - When ``fit`` is ``True`` the mechanic ``value -> code`` map is *learned*
          from the sorted distinct non-null fit-time ``mechanic`` values and
          written into ``schema.categorical_maps`` under
          :data:`PROMO_MECHANIC_COLUMN`; codes run ``1..N`` in sorted order so
          the same mechanic always maps to the same code (``0`` stays reserved).
        - When ``fit`` is ``False`` the *frozen* map already in
          ``schema.categorical_maps`` is reused, so a mechanic unseen at fit time
          (or a promo absent from the file) encodes to the reserved ``0``.

        Missing-promo handling: a lead whose ``promo_id`` is absent from the
        Promo_History_File gets mechanic code ``0`` (the reserved missing/unseen
        code) and ``threshold_php = 0``.

        Args:
            leads: The treated-lead frame; must carry a ``promo_id`` column.
            schema: The :class:`FeatureSchema` whose ``categorical_maps`` entry
                for ``mechanic`` is populated when ``fit`` is ``True`` and read
                when it is ``False``.
            fit: ``True`` to learn the mechanic map, ``False`` to reuse it.

        Returns:
            A frame indexed like ``leads`` with the ``mechanic`` code column and
            the ``threshold_php`` numeric pass-through.
        """
        promos = self._read_promo_history()

        # Learn or reuse the deterministic mechanic value -> code map
        # (Requirement 2.13). Codes run 1..N over the sorted distinct non-null
        # fit-time values; 0 stays reserved for missing/unseen -- mirrors the
        # DNA categorical encoding.
        if fit:
            distinct = sorted(promos[PROMO_MECHANIC_COLUMN].dropna().unique())
            schema.categorical_maps[PROMO_MECHANIC_COLUMN] = {
                value: code for code, value in enumerate(distinct, start=1)
            }

        # Index the promo frame by promo_id so leads can look up their row; a
        # duplicated promo_id in the source keeps the first occurrence so the
        # join stays one-to-one.
        promos_by_id = promos.drop_duplicates(subset="promo_id", keep="first")
        promos_by_id = promos_by_id.set_index("promo_id")

        block = pd.DataFrame(index=leads.index)

        # Mechanic code (Requirement 2.13): map each lead's promo's raw mechanic
        # through the frozen value -> code map; missing promos and mechanics
        # unseen at fit time fall through to the reserved 0.
        code_map = schema.categorical_maps.get(PROMO_MECHANIC_COLUMN, {})
        raw_mechanic = leads["promo_id"].map(promos_by_id[PROMO_MECHANIC_COLUMN])
        block[PROMO_MECHANIC_COLUMN] = raw_mechanic.map(code_map).fillna(0).astype(int)

        # threshold_php numeric pass-through (Requirement 2.13): look each lead's
        # value up by promo_id; absent promos become NaN -> filled 0.
        threshold = leads["promo_id"].map(promos_by_id[PROMO_THRESHOLD_COLUMN])
        block[PROMO_THRESHOLD_COLUMN] = pd.to_numeric(
            threshold, errors="coerce"
        ).fillna(0)

        return block

    def _assemble(
        self, leads: pd.DataFrame, schema: FeatureSchema, fit: bool
    ) -> pd.DataFrame:
        """Build every feature block and concatenate them into one frame.

        Shared by :meth:`fit_transform` and :meth:`transform`: calls each block
        with the given ``fit`` flag (so the same code path learns or reuses the
        schema), then concatenates the per-block frames -- all indexed like
        ``leads`` -- side by side. The returned frame carries every engineered
        column; the caller reindexes it onto the fixed ``schema.columns`` order.
        """
        blocks = [
            self._customer_dna_block(leads, schema, fit),
            self._active_product_count_block(leads, schema, fit),
            self._adb_block(leads, schema, fit),
            self._contact_history_block(leads, schema, fit),
            self._ndb_block(leads, schema, fit),
            self._part2_block(leads, schema, fit),
            self._promo_attributes_block(leads, schema, fit),
        ]
        return pd.concat(blocks, axis=1)

    def _final_columns(self, schema: FeatureSchema) -> list[str]:
        """Return the fixed final column order recorded in ``schema.columns``.

        The order is fixed by design (Requirements 2.1, 7.2) so training and
        scoring matrices line up exactly:

        DNA numeric -> DNA categorical codes -> ``Customer_DNA_Missing_Flag`` ->
        sorted product-type active counts -> ``latest_adb``, ``adb_trend``,
        ``ADB_Missing_Flag`` -> ``avg_contacts_per_month`` -> ``ndb_flag`` ->
        part2 columns -> ``Part2_Features_Missing_Flag`` -> ``mechanic`` code ->
        ``threshold_php``.

        The product-type and part2 column lists are the fit-time discovered
        orders already frozen on ``schema`` (``product_type_columns`` is sorted
        at discovery).
        """
        return (
            list(DNA_NUMERIC_COLUMNS)
            + list(DNA_CATEGORICAL_COLUMNS)
            + [CUSTOMER_DNA_MISSING_FLAG]
            + list(schema.product_type_columns)
            + [LATEST_ADB_COLUMN, ADB_TREND_COLUMN, ADB_MISSING_FLAG]
            + [AVG_CONTACTS_PER_MONTH_COLUMN]
            + [NDB_FLAG_COLUMN]
            + list(schema.part2_columns)
            + [PART2_FEATURES_MISSING_FLAG]
            + [PROMO_MECHANIC_COLUMN]
            + [PROMO_THRESHOLD_COLUMN]
        )

    def fit_transform(self, leads: pd.DataFrame) -> tuple[pd.DataFrame, FeatureSchema]:
        """Assemble the training feature matrix and learn the ``FeatureSchema``.

        Reads all approved sources, builds the per-lead feature blocks (Customer
        DNA, active product counts, ADB, contacts, NDB, part2 join, promo
        attributes) with ``fit=True`` so each *learns* its part of the schema
        (categorical ``value -> code`` maps, discovered product-type columns,
        part2 columns), records the fixed final column order into
        ``schema.columns``, and returns the aligned feature matrix ``X``
        reindexed onto that order alongside the fitted :class:`FeatureSchema`
        (Requirements 2.1, 7.2).

        Every source read routes through :func:`assert_not_answer_key`
        (Requirement 2.14) inside the per-block ``_read_*`` helpers.
        """
        schema = FeatureSchema()

        # Build every block in fit mode so the categorical maps, product-type
        # columns, and part2 columns are learned onto the fresh schema.
        assembled = self._assemble(leads, schema, fit=True)

        # Freeze the fixed final column order now that the discovered column
        # lists are known (Requirements 2.1, 7.2).
        schema.columns = self._final_columns(schema)

        # Reindex onto the authoritative order; every column exists after a fit
        # assembly, so this only orders (no zero-fill is needed here).
        X = assembled.reindex(columns=schema.columns)
        return X, schema

    def transform(self, leads: pd.DataFrame, schema: FeatureSchema) -> pd.DataFrame:
        """Assemble a feature matrix for new leads using a frozen schema.

        Rebuilds the same feature blocks as :meth:`fit_transform` for a new set
        of leads/clients but applies the *frozen* ``schema`` (``fit=False``) --
        reusing the learned categorical maps (unseen mechanic/DNA values map to
        the reserved ``0`` code), reindexing onto the exact ``schema.columns`` in
        order, and zero-filling any column the new data lacks. This is the
        stability contract behind Requirements 7.2 and 2.1.

        Every source read routes through :func:`assert_not_answer_key`
        (Requirement 2.14) inside the per-block ``_read_*`` helpers.
        """
        # Build every block in transform mode so the frozen maps and discovered
        # column lists are reused rather than relearned.
        assembled = self._assemble(leads, schema, fit=False)

        # Reindex onto the frozen authoritative order; a column absent from the
        # new data (e.g. a fit-time product_type with no rows now) is zero-filled
        # so the matrix matches the trained schema exactly (Requirements 2.1, 7.2).
        return assembled.reindex(columns=schema.columns, fill_value=0)
