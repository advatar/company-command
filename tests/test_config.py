from acme.config import Settings


def test_in_process_by_default():
    s = Settings.from_env({})
    assert s.durable is False
    assert s.effective_ledger_url is None
    assert s.rp_id == "localhost"


def test_durable_when_database_url_set():
    s = Settings.from_env({"ACME_DATABASE_URL": "postgresql://x/y"})
    assert s.durable is True
    assert s.effective_ledger_url == "postgresql://x/y"


def test_ledger_url_overrides():
    s = Settings.from_env({"ACME_DATABASE_URL": "postgresql://a/b",
                           "ACME_LEDGER_URL": "postgresql://c/d"})
    assert s.effective_ledger_url == "postgresql://c/d"


def test_model_map_parsing():
    s = Settings.from_env({"ACME_MODEL_MAP": "planner-high=llama-3.3, fast=qwen"})
    assert s.model_map == {"planner-high": "llama-3.3", "fast": "qwen"}
