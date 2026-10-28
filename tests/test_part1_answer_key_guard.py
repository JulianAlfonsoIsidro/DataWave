"""Answer-key-prohibition guard tests for the Part1_Optin_Pipeline (task 3.3).

Requirement 2.14 is absolute: the pipeline must never read, open, or use any
Answer_Key_File (a file whose name contains the substring ``_answer_key``).
This module enforces that prohibition three ways:

1. **Direct guard-helper tests.** ``assert_not_answer_key`` is the runtime
   invariant behind Requirement 2.14 -- it raises ``ValueError`` for any path
   containing the marker and returns the path unchanged otherwise. These tests
   pin that behaviour down directly.
2. **Recorded-read test.** Every path handed to ``pandas.read_csv`` or the
   builtin ``open`` during a representative assembly is recorded via
   monkeypatching, and the recorded paths are asserted to contain no marker.
   The full ``Feature_Assembler.fit_transform`` lands in later tasks (4.x/5.x);
   until then the recorder also drives the guard directly so the "paths the
   assembler opens are clean" contract is exercised on the surface runnable now
   and the harness is ready to wrap ``fit_transform`` once it exists.
3. **Repo-grep test.** The ``part1_optin`` package source and the part1 test
   suite are scanned line-by-line; a line is a violation only if it references
   the marker *as a file path or read* (alongside ``.csv`` or ``read_csv(``),
   so the legitimate ``ANSWER_KEY_MARKER`` constant / guard logic / docstrings
   describing the prohibition are not flagged.

The marker constant is never spelled as a literal source string in this module
(it is imported from ``part1_optin.config``) and no test here references a
``*_answer_key*`` file as an actual path -- any forbidden path used to exercise
the *rejection* behaviour is built by concatenating the imported marker so the
file itself stays clean under its own grep.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pandas as pd
import pytest

from part1_optin.config import ANSWER_KEY_MARKER, Config
from part1_optin.features import Feature_Assembler, assert_not_answer_key

# A sample of the eight approved Config source paths -- all legitimate and
# marker-free -- used to confirm the guard passes clean paths through.
_APPROVED_PATHS = [
    Config().promo_leads_path,
    Config().customer_dna_path,
    Config().product_ownership_path,
    Config().adb_monthly_path,
    Config().contact_history_path,
    Config().ndb_path,
    Config().features_part2_path,
    Config().promo_history_path,
]

# A forbidden path built from the imported marker so this test file never
# contains a literal "_answer_key" file reference of its own (keeps it clean
# under the repo-grep test below). e.g. "data/<marker>_clients.csv".
_FORBIDDEN_PATH = Path("data") / (ANSWER_KEY_MARKER + "_clients.csv")


# ---------------------------------------------------------------------------
# 1. Direct guard-helper tests
# ---------------------------------------------------------------------------


def test_guard_rejects_path_containing_marker() -> None:
    """A path containing the marker raises ValueError (Requirement 2.14)."""
    with pytest.raises(ValueError) as excinfo:
        assert_not_answer_key(_FORBIDDEN_PATH)

    # The error should name the marker so the violation is obvious.
    assert ANSWER_KEY_MARKER in str(excinfo.value)


def test_guard_rejects_marker_anywhere_in_path() -> None:
    """The marker is caught in any path component, not just the final name."""
    nested = Path("data") / (ANSWER_KEY_MARKER + "_dir") / "clients.csv"

    with pytest.raises(ValueError):
        assert_not_answer_key(nested)


def test_guard_rejects_string_path() -> None:
    """A ``str`` path (not just ``Path``) containing the marker is rejected."""
    with pytest.raises(ValueError):
        assert_not_answer_key("data/" + ANSWER_KEY_MARKER + "_promos.csv")


def test_guard_returns_approved_paths_unchanged() -> None:
    """Every approved source path passes and is returned as a ``Path``."""
    for path in _APPROVED_PATHS:
        returned = assert_not_answer_key(path)
        assert returned == Path(path)
        assert ANSWER_KEY_MARKER not in str(returned)


def test_guard_return_value_is_usable_inline() -> None:
    """The guard returns the path so call sites can wrap a read inline."""
    path = Config().customer_dna_path
    assert assert_not_answer_key(path) == Path(path)


# ---------------------------------------------------------------------------
# 2. Recorded-read test (monkeypatch pandas.read_csv / open)
# ---------------------------------------------------------------------------


class _ReadRecorder:
    """Records every path passed to ``pandas.read_csv`` / builtin ``open``.

    Installed over both readers for the duration of a representative assembly;
    afterwards :meth:`assert_no_answer_key` checks that none of the recorded
    paths contain the marker, directly verifying Requirement 2.14 at the I/O
    boundary.
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
        # Only path-like targets are of interest; file descriptors / buffers
        # carry no filesystem name to violate the prohibition.
        if isinstance(target, (str, Path)):
            self.paths.append(str(target))

    def assert_no_answer_key(self) -> None:
        offenders = [p for p in self.paths if ANSWER_KEY_MARKER in p]
        assert not offenders, (
            f"Requirement 2.14 violated: assembly opened answer-key path(s) "
            f"{offenders!r}"
        )


def test_assembly_opens_no_answer_key_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A representative assembly opens no path containing the marker (2.14).

    ``Feature_Assembler.fit_transform`` is implemented in later tasks (4.x/5.x);
    until it reads sources, this recorder is driven over the runnable guard
    surface so the "no ``_answer_key`` path is ever opened" contract is
    exercised now and the harness is ready to wrap ``fit_transform`` verbatim
    once it exists. The approved paths route through the guard (as the real
    assembler will), the recorder captures the reads, and none may carry the
    marker.
    """
    recorder = _ReadRecorder().install(monkeypatch)

    # Stand in for the real reads fit_transform will perform: route each
    # approved source through the guard, then read it through the (recorded)
    # pandas.read_csv exactly as the assembler will. Paths that do not exist on
    # disk are tolerated -- the point is to record which paths are opened, not
    # to parse them.
    for path in _APPROVED_PATHS:
        guarded = assert_not_answer_key(path)
        try:
            pd.read_csv(guarded)
        except (FileNotFoundError, OSError, pd.errors.EmptyDataError, ValueError):
            # The recorder already captured the path before the read failed;
            # absence or unparseable content on disk is irrelevant here.
            pass

    recorder.assert_no_answer_key()
    # The recorder must actually have observed the approved reads, otherwise
    # the assertion above would pass vacuously.
    assert recorder.paths, "expected the recorder to capture at least one read"


def test_recorder_would_flag_a_forbidden_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorder's check fails if a marker path is ever opened.

    Guards against a vacuous pass of :func:`test_assembly_opens_no_answer_key_path`
    by proving the recorder genuinely detects a violating read.
    """
    recorder = _ReadRecorder().install(monkeypatch)

    try:
        pd.read_csv(_FORBIDDEN_PATH)
    except Exception:
        # The path is recorded before any read error; the file need not exist.
        pass

    with pytest.raises(AssertionError):
        recorder.assert_no_answer_key()


def test_feature_assembler_reads_only_config_sources() -> None:
    """The assembler is constructed from Config (the only source of paths).

    The assembler reads exclusively the eight approved ``Config`` paths; none
    of those defaults carries the marker, so an assembler built from a default
    ``Config`` can reference no answer-key file (Requirement 2.14).
    """
    assembler = Feature_Assembler(Config())
    config_paths = [
        assembler.config.promo_leads_path,
        assembler.config.customer_dna_path,
        assembler.config.product_ownership_path,
        assembler.config.adb_monthly_path,
        assembler.config.contact_history_path,
        assembler.config.ndb_path,
        assembler.config.features_part2_path,
        assembler.config.promo_history_path,
    ]
    for path in config_paths:
        assert ANSWER_KEY_MARKER not in str(path)


# ---------------------------------------------------------------------------
# 3. Repo-grep test
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_DIR = _REPO_ROOT / "src" / "part1_optin"
_TESTS_DIR = _REPO_ROOT / "tests"


def _part1_source_files() -> list[Path]:
    """Collect the part1 package sources and the part1 test suite files.

    Scope matches task 3.3: ``src/part1_optin/*.py``, ``tests/test_part1_*.py``,
    and ``tests/strategies_part1.py``. ``__pycache__`` is excluded.
    """
    files: list[Path] = []
    files.extend(
        p for p in _PACKAGE_DIR.glob("*.py") if p.is_file()
    )
    files.extend(sorted(_TESTS_DIR.glob("test_part1_*.py")))
    strategies = _TESTS_DIR / "strategies_part1.py"
    if strategies.is_file():
        files.append(strategies)
    return files


# Legitimate identifiers whose spelling embeds the ``_answer_key`` substring:
# the guard helper name and the marker constant name. These are the sanctioned
# "guard logic" references task 3.3 must NOT flag, so they are neutralized out
# of a line before the forbidden-path check runs. ``read_csv`` is also
# neutralized because it embeds ``_csv`` -- not the marker, but removing the
# bare call token keeps the remaining check focused on an actual ``.csv`` path.
_SANCTIONED_TOKENS = (
    "assert_not_answer_key",
    "ANSWER_KEY_MARKER",
)


def _is_forbidden_reference(line: str) -> bool:
    """Return True only for a marker reference that looks like a file path/read.

    A line violates Requirement 2.14 when, *after removing the sanctioned guard
    identifiers* (``assert_not_answer_key``, ``ANSWER_KEY_MARKER``), it still
    names the marker ``_answer_key`` AND looks like a concrete file path or read
    -- i.e. it also contains ``.csv`` or ``read_csv(``. This flags a real
    ``_answer_key`` *file reference* while leaving the marker constant
    definition, the guard helper usage, and prose/docstrings describing the
    prohibition untouched (they carry no residual marker once the sanctioned
    identifiers are stripped).
    """
    residual = line
    for token in _SANCTIONED_TOKENS:
        residual = residual.replace(token, "")
    if ANSWER_KEY_MARKER not in residual:
        return False
    return ".csv" in residual or "read_csv(" in residual


def test_part1_sources_contain_no_answer_key_path_reference() -> None:
    """No part1 source/test line references an answer-key file path (2.14).

    Scans every part1 package and test line; a line is a violation only when it
    pairs the marker with a file-path/read token, so the marker *constant* and
    docstrings describing the prohibition pass while a real ``_answer_key`` file
    reference would fail.
    """
    files = _part1_source_files()
    # Sanity: the package and strategies module must be in scope, else the scan
    # would pass vacuously.
    assert files, "expected to find part1 source/test files to scan"

    offenders: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_forbidden_reference(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Requirement 2.14 violated: answer-key file path reference(s) found:\n"
        + "\n".join(offenders)
    )


def test_grep_detector_flags_a_synthetic_violation() -> None:
    """The detector flags a marker reference that looks like a file read.

    Proves :func:`test_part1_sources_contain_no_answer_key_path_reference` is
    not vacuous: a synthetic line pairing the marker with a ``.csv`` path is
    detected, while a marker-only constant assignment is not.
    """
    violating = 'pd.read_csv("data/' + ANSWER_KEY_MARKER + '_clients.csv")'
    constant_only = "ANSWER_KEY_MARKER = marker_value  # mentions the prohibition"

    assert _is_forbidden_reference(violating)
    assert not _is_forbidden_reference(constant_only)
