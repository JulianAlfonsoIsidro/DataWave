"""Part1 opt-in test anchor.

Confirms the ``part1_optin`` package and its modules import cleanly. Part1 test
files live alongside the part2 suite under ``tests/`` and are named
``test_part1_*.py`` to avoid colliding with the part2 tests.
"""


def test_part1_optin_package_imports():
    import part1_optin  # noqa: F401
    from part1_optin import (  # noqa: F401
        config,
        leads,
        features,
        model,
        validation,
        explain,
        scoring,
        main,
    )
