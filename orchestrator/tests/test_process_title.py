import sys
import types

import pytest

from orchestrator.process_title import (
    DEFAULT_PROCESS_NAME,
    apply_process_name,
    resolve_process_name,
)


def test_resolve_default_when_unset():
    assert resolve_process_name({}) == DEFAULT_PROCESS_NAME == "producer-desk-orchestrator"


def test_resolve_env_override():
    assert resolve_process_name({"ORCHESTRATOR_PROCESS_NAME": "my-orch"}) == "my-orch"


@pytest.mark.parametrize("value", ["", "   "])
def test_resolve_empty_disables(value):
    assert resolve_process_name({"ORCHESTRATOR_PROCESS_NAME": value}) is None


@pytest.fixture
def fake_setproctitle(monkeypatch):
    calls = []
    module = types.ModuleType("setproctitle")
    module.setproctitle = calls.append
    monkeypatch.setitem(sys.modules, "setproctitle", module)
    return calls


def test_apply_sets_title(fake_setproctitle):
    assert apply_process_name({"ORCHESTRATOR_PROCESS_NAME": "my-orch"}) == "my-orch"
    assert fake_setproctitle == ["my-orch"]


def test_apply_default(fake_setproctitle):
    assert apply_process_name({}) == DEFAULT_PROCESS_NAME
    assert fake_setproctitle == [DEFAULT_PROCESS_NAME]


def test_apply_empty_does_nothing(fake_setproctitle):
    assert apply_process_name({"ORCHESTRATOR_PROCESS_NAME": ""}) is None
    assert fake_setproctitle == []


def test_apply_without_setproctitle_does_not_raise(monkeypatch, caplog):
    # sys.modulesにNoneを入れるとimportはImportErrorになる（未インストール相当）。
    monkeypatch.setitem(sys.modules, "setproctitle", None)
    with caplog.at_level("WARNING"):
        assert apply_process_name({}) is None
    assert "setproctitle" in caplog.text


def test_apply_setproctitle_error_does_not_raise(monkeypatch):
    module = types.ModuleType("setproctitle")

    def boom(_name):
        raise RuntimeError("boom")

    module.setproctitle = boom
    monkeypatch.setitem(sys.modules, "setproctitle", module)
    assert apply_process_name({}) is None
