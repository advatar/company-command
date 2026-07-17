import pytest

from comcmd.kernel import durable


def test_durable_engine_requires_dsn():
    # With dbos installed but no DSN, the guard must fail loudly rather than
    # silently degrade to non-durable execution.
    if not durable.dbos_available():
        pytest.skip("dbos not installed")
    with pytest.raises(RuntimeError):
        durable.make_durable_engine(dsn=None)
