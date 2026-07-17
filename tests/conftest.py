import os
import sys
from pathlib import Path

import pytest

# Make the repo root importable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def dbos_engine():
    """One DBOS engine per test session — DBOS is a process-wide singleton, so it
    can be launched only once. Shared across all DBOS-backed tests."""
    dsn = os.environ.get("COMCMD_TEST_DBOS_URL")
    if not dsn:
        pytest.skip("COMCMD_TEST_DBOS_URL not set")
    from comcmd.kernel.dbos_engine import DbosEngine
    eng = DbosEngine(dsn, name="comcmd-tests")
    yield eng
    eng.shutdown()
