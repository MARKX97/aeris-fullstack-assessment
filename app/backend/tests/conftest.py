"""Make app/backend importable (``main``, ``store``) for the test suite.

The root pyproject.toml uses ``--import-mode=importlib`` so that A/ and B/
test files can share basenames; a side effect is that the test file's own
directory is not added to ``sys.path``. Inserting the backend directory
here keeps ``python3 -m pytest app/backend`` working from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
