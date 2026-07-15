import pytest

from acme.kernel import durable


def test_durability_is_honestly_gated():
    # The optional dbos dependency is not installed in the default env; the guard
    # must fail loudly rather than silently degrade to non-durable execution.
    assert durable.dbos_available() is False
    with pytest.raises(RuntimeError):
        durable.require_durable_backend(dsn="postgres://x")
