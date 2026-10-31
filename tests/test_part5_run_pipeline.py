"""Example unit tests for the Pipeline_Runner stage ordering.

These cover the two orchestration behaviors of ``src/run_pipeline.py``
(Requirements 1.1, 1.2):

- on a clean run the four stages execute in the fixed dependency order
  ``part2_network`` -> ``part1_optin`` -> ``part3_segments`` -> ``part4_cards``
  and ``main`` returns 0 (Requirement 1.1), and
- a stage returning a non-zero exit code halts the run: ``main`` returns that
  code and no later stage is invoked (Requirement 1.2).

Each stage's ``main`` is monkeypatched with a fake that records its name, so
the real Part 1-4 pipelines never run. These are concrete example tests, not
Hypothesis properties.
"""

from __future__ import annotations

import part1_optin.main as part1_main
import part2_network.main as part2_main
import part3_segments.main as part3_main
import part4_cards.main as part4_main
import run_pipeline

# The stage modules in the order run_pipeline invokes their ``main``; the tuple
# of names is the expected call order on a clean run (Requirement 1.1).
STAGE_MODULES = (
    ("part2_network", part2_main),
    ("part1_optin", part1_main),
    ("part3_segments", part3_main),
    ("part4_cards", part4_main),
)
EXPECTED_ORDER = [name for name, _ in STAGE_MODULES]


def _patch_stages(monkeypatch, calls, exit_codes):
    """Replace each stage's ``main`` with a fake recording its name.

    ``calls`` is a shared list every fake appends its stage name to when
    invoked; ``exit_codes`` maps a stage name to the exit code its fake returns
    (default 0). The fakes assert they are called with ``[]`` just as
    run_pipeline invokes ``module.main([])``.
    """

    def make_fake(stage_name):
        def fake_main(argv):
            assert argv == []
            calls.append(stage_name)
            return exit_codes.get(stage_name, 0)

        return fake_main

    for name, module in STAGE_MODULES:
        monkeypatch.setattr(module, "main", make_fake(name))


def test_clean_run_runs_all_stages_in_order(monkeypatch):
    """A clean run invokes the four stages in order and returns 0.

    Every stage returns 0, so run_pipeline.main must call all four in the fixed
    dependency order (part2_network first) and return 0 (Requirement 1.1).
    """
    calls = []
    _patch_stages(monkeypatch, calls, exit_codes={})

    code = run_pipeline.main()

    assert code == 0
    assert calls == EXPECTED_ORDER


def test_middle_stage_failure_halts_and_returns_its_code(monkeypatch):
    """A non-zero middle stage stops the run before any later stage.

    The second stage (part1_optin) returns 7; run_pipeline.main must return 7
    and only the stages up to and including the failing one may have run, so no
    later stage (part3_segments, part4_cards) is invoked (Requirement 1.2).
    """
    calls = []
    _patch_stages(monkeypatch, calls, exit_codes={"part1_optin": 7})

    code = run_pipeline.main()

    assert code == 7
    assert calls == ["part2_network", "part1_optin"]


def test_first_stage_failure_runs_only_that_stage(monkeypatch):
    """A non-zero first stage returns its code with nothing else run.

    The first stage (part2_network) returns 3; run_pipeline.main must return 3
    and no other stage may be invoked (Requirement 1.2).
    """
    calls = []
    _patch_stages(monkeypatch, calls, exit_codes={"part2_network": 3})

    code = run_pipeline.main()

    assert code == 3
    assert calls == ["part2_network"]
