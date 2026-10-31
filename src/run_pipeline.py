"""Pipeline_Runner: run the four batch pipelines end to end in order.

This orchestrator regenerates the on-disk artifacts the Part 5 webapp reads
(the fitted Part 1 model under ``outputs/`` and ``outputs/cards.json``) by
invoking each package's ``main([])`` in-process, in dependency order
(Requirement 1.1):

1. ``part2_network`` -- build the network Features_File.
2. ``part1_optin``   -- fit/calibrate the Part 1 model and score.
3. ``part3_segments``-- assign the four segment labels.
4. ``part4_cards``   -- build the action Cards and sendable-lead CSVs.

A stage returning a non-zero exit code stops the run: the Pipeline_Runner
surfaces that stage's failure and returns its code before the next stage runs,
so no later stage executes (Requirement 1.2). A clean run returns 0.

Each stage is resolved from its module's ``main`` attribute at call time, so a
test can ``monkeypatch.setattr`` any stage module's ``main`` and have the
substitution honored. The module ends with the standard
``if __name__ == "__main__": raise SystemExit(main())`` guard, so it runs as
``python src/run_pipeline.py`` (or ``python -m run_pipeline``) with
``PYTHONPATH=src``.
"""

from __future__ import annotations

import sys

from part1_optin import main as part1_main
from part2_network import main as part2_main
from part3_segments import main as part3_main
from part4_cards import main as part4_main

# The four stages in dependency order (Requirement 1.1). Each entry pairs a
# human-readable stage name with the module whose ``main`` is invoked; resolving
# ``module.main`` at call time keeps monkeypatching each stage's ``main``
# effective.
_STAGES = (
    ("part2_network", part2_main),
    ("part1_optin", part1_main),
    ("part3_segments", part3_main),
    ("part4_cards", part4_main),
)


def main(argv: list[str] | None = None) -> int:
    """Run the four batch pipelines in order and return a process exit code.

    Invokes each stage's ``main([])`` in the fixed order part2_network ->
    part1_optin -> part3_segments -> part4_cards (Requirement 1.1). If a stage
    returns a non-zero exit code, the run stops immediately: that stage's
    failure is reported to stderr and its code is returned before the next
    stage runs, so no later stage executes (Requirement 1.2). A clean run
    returns 0.

    ``argv`` is accepted for a uniform entry-point signature; each stage is run
    with its own defaults (``[]``), matching the one-command pipeline run.
    """
    for name, module in _STAGES:
        code = module.main([])
        if code != 0:
            print(
                f"error: stage {name!r} failed with exit code {code}; "
                "stopping the pipeline",
                file=sys.stderr,
            )
            return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
