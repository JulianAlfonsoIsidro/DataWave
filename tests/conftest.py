"""Pytest configuration: make the ``src`` layout importable.

Adds the project's ``src`` directory to ``sys.path`` so tests can use the
absolute import ``from part2_network... import ...`` without requiring the
caller to set ``PYTHONPATH``.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
