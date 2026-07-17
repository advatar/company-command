from comcmd.kernel.ledger import Ledger
from comcmd.kernel.records import Event, EventType


def _ev(company="c1", i=0):
    return Event(type=EventType.step_succeeded, company=company,
                 task_id="t1", payload={"step": f"s{i}"})


def test_append_and_verify_chain():
    led = Ledger(":memory:")
    for i in range(5):
        led.append(_ev(i=i))
    assert led.verify_chain("c1") is True
    events = list(led.read("c1"))
    assert [e.event.payload["step"] for e in events] == [f"s{i}" for i in range(5)]


def test_chain_links_prev_seal():
    led = Ledger(":memory:")
    a = led.append(_ev(i=0))
    b = led.append(_ev(i=1))
    assert b.prev_seal == a.seal
    assert a.prev_seal.endswith("0" * 64)  # genesis


def test_tamper_detected(tmp_path):
    import sqlite3

    path = tmp_path / "l.sqlite"
    led = Ledger(str(path))
    for i in range(3):
        led.append(_ev(i=i))
    led.close()
    # Rewrite a stored event body out from under the seal.
    conn = sqlite3.connect(str(path))
    conn.execute("UPDATE events SET body=? WHERE seq=2",
                 ('{"type":"step_succeeded","company":"c1","task_id":"t1",'
                  '"payload":{"step":"TAMPERED"}}',))
    conn.commit()
    conn.close()
    led2 = Ledger(str(path))
    assert led2.verify_chain("c1") is False


def test_per_company_isolation():
    led = Ledger(":memory:")
    led.append(_ev(company="a", i=0))
    led.append(_ev(company="b", i=0))
    assert led.verify_chain("a") and led.verify_chain("b")
    assert len(list(led.read("a"))) == 1
