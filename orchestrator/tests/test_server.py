"""orchestrator.server の単体テスト。実際にループバックでHTTPリクエストを送って検証する。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from orchestrator.aggregation import ActivityEvent, AggregatedState, IssueSummary
from orchestrator.server import StateStore, make_server


def _run_server_in_background(store: StateStore):
    server = make_server(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path: str) -> tuple[int, dict]:
    host, port = server.server_address[0], server.server_address[1]
    with urllib.request.urlopen(f"http://{host}:{port}{path}") as response:
        return response.status, json.loads(response.read())


def test_state_store_returns_none_before_any_update() -> None:
    store = StateStore()

    assert store.get() is None


def test_state_store_returns_latest_set_state() -> None:
    store = StateStore()
    state = AggregatedState(decisions=[], activity=[])

    store.set(state)

    assert store.get() is state


def test_get_api_state_returns_empty_lists_before_first_poll() -> None:
    store = StateStore()
    server, _ = _run_server_in_background(store)
    try:
        status, body = _get(server, "/api/state")
        assert status == 200
        assert body == {"decisions": [], "activity": []}
    finally:
        server.shutdown()


def test_get_api_state_returns_latest_aggregated_state() -> None:
    store = StateStore()
    store.set(
        AggregatedState(
            decisions=[
                IssueSummary(
                    repo="nosetech/project-a",
                    number=1,
                    title="t",
                    labels=["needs-human-decision"],
                    comments=[],
                    updated_at="2026-08-01T00:00:00Z",
                )
            ],
            activity=[
                ActivityEvent(
                    repo="nosetech/project-a",
                    number=1,
                    title="t",
                    label="needs-human-decision",
                    updated_at="2026-08-01T00:00:00Z",
                )
            ],
        )
    )
    server, _ = _run_server_in_background(store)
    try:
        status, body = _get(server, "/api/state")
        assert status == 200
        assert body["decisions"][0]["number"] == 1
        assert body["activity"][0]["label"] == "needs-human-decision"
    finally:
        server.shutdown()


def test_unknown_path_returns_404() -> None:
    store = StateStore()
    server, _ = _run_server_in_background(store)
    try:
        try:
            _get(server, "/unknown")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        else:
            raise AssertionError("expected HTTPError")
    finally:
        server.shutdown()
