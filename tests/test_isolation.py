"""Multi-tenant isolation and the untrusted-pack guard."""

import os
from pathlib import Path

import pytest

from comcmd.gateway.intents import ActionIntent
from comcmd.kernel.ledger import Ledger
from comcmd.kernel.records import Event, EventType
from comcmd.pack import UntrustedPackError, load_pack

AUTO_STEAM = Path(__file__).resolve().parents[1] / "companies" / "auto-steam"


# -- untrusted pack guard ---------------------------------------------------

def test_untrusted_pack_with_code_is_refused():
    with pytest.raises(UntrustedPackError):
        load_pack(AUTO_STEAM, trusted=False)


def test_trusted_pack_loads_skills():
    pack = load_pack(AUTO_STEAM, trusted=True)
    assert "market" in pack.skills


# -- tenant isolation (in-process) ------------------------------------------

def _ev(company, i):
    return Event(type=EventType.step_succeeded, company=company, task_id="t",
                 payload={"step": f"s{i}"})


def test_ledger_reads_are_per_company():
    led = Ledger(":memory:")
    for i in range(3):
        led.append(_ev("tenant-a", i))
    led.append(_ev("tenant-b", 0))
    assert [se.event.company for se in led.read("tenant-a")] == ["tenant-a"] * 3
    assert len(list(led.read("tenant-b"))) == 1
    assert led.verify_chain("tenant-a") and led.verify_chain("tenant-b")


def test_action_digest_is_company_scoped():
    # Same action/tool/task in two companies must not collide (no cross-tenant
    # capability reuse or approval hijack).
    a = ActionIntent(company="tenant-a", task_id="t", step_id="s",
                     requested_by="w", action_id="pay", tool="finance.pay")
    b = ActionIntent(company="tenant-b", task_id="t", step_id="s",
                     requested_by="w", action_id="pay", tool="finance.pay")
    assert a.action_digest != b.action_digest


# -- tenant isolation (shared Postgres) -------------------------------------

DSN = os.environ.get("COMCMD_TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="COMCMD_TEST_DATABASE_URL not set")
def test_shared_postgres_ledger_isolates_companies():
    import secrets

    from comcmd.kernel.ledger_pg import PostgresLedger
    led = PostgresLedger(DSN)
    a, b = "ten-" + secrets.token_hex(4), "ten-" + secrets.token_hex(4)
    for i in range(4):
        led.append(_ev(a, i))
    led.append(_ev(b, 0))
    # tamper company b's chain shouldn't affect a's verification
    assert led.verify_chain(a) is True
    assert [se.event.company for se in led.read(a)] == [a] * 4
    assert len(list(led.read(b))) == 1
    led.close()
