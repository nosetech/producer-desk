"""ダッシュボードからの画像・動画添付（issue #301）のテスト。"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest

from orchestrator.github_client import (
    BOT_COMMENT_MARKER,
    create_issue_with_attachments,
    gh_issue_create_supports_attach,
    post_comment_with_attachments,
)
from orchestrator.instruct import handle_create_issue, handle_instruct
from orchestrator.labels import STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION, STATUS_TODO
from orchestrator.media_uploads import (
    ATTACHMENT_PATHS_HEADING,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    MediaAttachmentError,
    SavedAttachment,
    append_attachment_paths,
    cleanup_after_run,
    cleanup_stale_uploads,
    decode_attachments,
    extract_attachment_paths,
    remove_saved,
    save_attachments,
)
from orchestrator.server import StateStore
from tests.test_server import (
    PROJECT_A,
    FakeComments,
    FakeIssueCreator,
    FakeLabels,
    _post,
    _recording_dispatch_queue,
    _run_server,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
MOV = b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 16
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16


def _att(name: str, data: bytes) -> dict:
    return {"name": name, "mimeType": "", "dataBase64": base64.b64encode(data).decode()}


# --- 検証 ---


@pytest.mark.parametrize(
    ("name", "data", "ext"),
    [
        ("a.png", PNG, "png"),
        ("a.JPG", JPG, "jpg"),
        ("a.jpeg", JPG, "jpg"),
        ("a.gif", GIF, "gif"),
        ("a.mp4", MP4, "mp4"),
        ("a.mov", MOV, "mov"),
        ("a.webm", WEBM, "webm"),
    ],
)
def test_decode_accepts_supported_formats(name: str, data: bytes, ext: str) -> None:
    [decoded] = decode_attachments([_att(name, data)])
    assert decoded.ext == ext
    assert decoded.data == data


def test_decode_empty_or_missing_returns_empty() -> None:
    assert decode_attachments(None) == []
    assert decode_attachments([]) == []


@pytest.mark.parametrize("name", ["a.svg", "a.pdf", "a.txt", "noext"])
def test_decode_rejects_unsupported_formats(name: str) -> None:
    with pytest.raises(MediaAttachmentError, match="対応していない形式"):
        decode_attachments([_att(name, PNG)])


def test_decode_rejects_magic_byte_mismatch() -> None:
    with pytest.raises(MediaAttachmentError, match="一致しません"):
        decode_attachments([_att("fake.png", b"<svg onload=alert(1)>")])


def test_decode_rejects_invalid_base64() -> None:
    with pytest.raises(MediaAttachmentError, match="base64"):
        decode_attachments([{"name": "a.png", "dataBase64": "!!!"}])


def test_decode_rejects_oversized_file() -> None:
    big = PNG + b"\x00" * MAX_ATTACHMENT_BYTES
    with pytest.raises(MediaAttachmentError, match="10MB"):
        decode_attachments([_att("big.png", big)])


def test_decode_rejects_too_many_files() -> None:
    with pytest.raises(MediaAttachmentError, match="件まで"):
        decode_attachments([_att(f"{i}.png", PNG) for i in range(MAX_ATTACHMENTS + 1)])


def test_decode_rejects_total_over_limit() -> None:
    nine_mb = MP4 + b"\x00" * (9 * 1024 * 1024)
    with pytest.raises(MediaAttachmentError, match="合計"):
        decode_attachments([_att(f"{i}.mp4", nine_mb) for i in range(6)])


# --- 保存・パスの受け渡し・後片付け ---


def test_save_uses_server_side_names(tmp_path: Path) -> None:
    decoded = decode_attachments([_att("../../etc/passwd.png", PNG)])
    [saved] = save_attachments("owner/repo", "12", decoded, base_dir=tmp_path)
    assert saved.path.parent == (tmp_path / "owner__repo" / "12").resolve()
    assert saved.path.suffix == ".png"
    assert "passwd" not in saved.path.name
    assert saved.path.read_bytes() == PNG


def test_append_and_extract_paths_roundtrip(tmp_path: Path) -> None:
    saved = [
        SavedAttachment(name="画面 → 崩れ.png", path=tmp_path / "a.png"),
        SavedAttachment(name="録画.mov", path=tmp_path / "b.mov"),
    ]
    message = append_attachment_paths("直してください", saved)
    assert message.startswith("直してください\n\n" + ATTACHMENT_PATHS_HEADING)
    assert f"- 録画.mov → {tmp_path / 'b.mov'}" in message
    assert extract_attachment_paths(message) == [tmp_path / "a.png", tmp_path / "b.mov"]
    assert append_attachment_paths("本文", []) == "本文"
    assert extract_attachment_paths("本文") == []


def test_cleanup_after_run_removes_files_and_empty_dir(tmp_path: Path) -> None:
    saved = save_attachments(
        "o/r", "3", decode_attachments([_att("a.png", PNG)]), base_dir=tmp_path
    )
    message = append_attachment_paths("x", saved)
    cleanup_after_run(message, base_dir=tmp_path)
    assert not saved[0].path.exists()
    assert not saved[0].path.parent.exists()


def test_remove_saved_ignores_paths_outside_base(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    base = tmp_path / "uploads"
    base.mkdir()
    remove_saved([outside], base_dir=base)
    assert outside.exists()


def test_cleanup_stale_uploads_removes_only_old_files(tmp_path: Path) -> None:
    old = save_attachments("o/r", "1", decode_attachments([_att("a.png", PNG)]), base_dir=tmp_path)
    new = save_attachments("o/r", "2", decode_attachments([_att("b.png", PNG)]), base_dir=tmp_path)
    now = 1_000_000_000.0
    os.utime(old[0].path, (now - 8 * 86400, now - 8 * 86400))
    os.utime(new[0].path, (now - 86400, now - 86400))
    assert cleanup_stale_uploads(base_dir=tmp_path, now=now) == 1
    assert not old[0].path.exists()
    assert not old[0].path.parent.exists()
    assert new[0].path.exists()


# --- ghコマンドの組み立て ---


class _Run:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "err")


def test_post_comment_with_attachments_builds_gh_command() -> None:
    run = _Run()
    post_comment_with_attachments("o/r", 5, "見てください", ["/t/a.png", "/t/b.mov"], run=run)
    [(args, kwargs)] = run.calls
    assert args == [
        "gh",
        "issue",
        "comment",
        "5",
        "--repo",
        "o/r",
        "--body-file",
        "-",
        "--attach",
        "/t/a.png",
        "--attach",
        "/t/b.mov",
    ]
    assert kwargs["input"] == f"見てください\n\n{BOT_COMMENT_MARKER}"
    assert kwargs["check"] is True


def test_post_comment_with_attachments_rejects_hash_in_path() -> None:
    with pytest.raises(ValueError):
        post_comment_with_attachments("o/r", 5, "x", ["/t/a#b.png"], run=_Run())


def test_create_issue_with_attachments_builds_gh_command_and_parses_number() -> None:
    run = _Run(stdout="https://github.com/o/r/issues/42\n")
    number = create_issue_with_attachments("o/r", "題", "本文", ["/t/a.png"], run=run)
    assert number == 42
    [(args, kwargs)] = run.calls
    assert args == [
        "gh",
        "issue",
        "create",
        "--repo",
        "o/r",
        "--title",
        "題",
        "--body-file",
        "-",
        "--attach",
        "/t/a.png",
    ]
    assert kwargs["input"] == "本文"


def test_create_issue_with_attachments_partial_failure_returns_created_issue() -> None:
    run = _Run(stdout="https://github.com/o/r/issues/7\n", returncode=1)
    assert create_issue_with_attachments("o/r", "t", "b", ["/t/a.png"], run=run) == 7


def test_create_issue_with_attachments_raises_without_url() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        create_issue_with_attachments("o/r", "t", "b", ["/t/a.png"], run=_Run(returncode=1))


def test_gh_issue_create_supports_attach_reads_help() -> None:
    assert gh_issue_create_supports_attach(run=_Run(stdout="  --attach file  Attach")) is True
    assert gh_issue_create_supports_attach(run=_Run(stdout="  --body string")) is False


# --- instruct / create issue ---


class _DQ:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, int, str]] = []

    def enqueue(self, repo: str, n: int, message: str) -> None:
        self.enqueued.append((repo, n, message))


def _saved(tmp_path: Path) -> list[SavedAttachment]:
    return [SavedAttachment(name="画面.png", path=tmp_path / "x.png")]


def test_handle_instruct_with_attachments_posts_attach_and_appends_paths(tmp_path: Path) -> None:
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    posted: list[tuple] = []
    plain: list[tuple] = []
    dq = _DQ()
    result = handle_instruct(
        "o/r",
        1,
        "instruct",
        "",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=lambda *a: plain.append(a),
        dispatch_queue=dq,  # type: ignore[arg-type]
        attachments=_saved(tmp_path),
        post_comment_with_attachments=lambda *a: posted.append(a),
    )
    assert result.dispatched is True
    assert plain == []
    assert posted == [("o/r", 1, "", [str(tmp_path / "x.png")])]
    [(_, _, message)] = dq.enqueued
    assert message == f"{ATTACHMENT_PATHS_HEADING}\n- 画面.png → {tmp_path / 'x.png'}"


def test_handle_instruct_without_attachments_is_unchanged() -> None:
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    dq = _DQ()
    handle_instruct(
        "o/r",
        1,
        "instruct",
        "進めて",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dq,  # type: ignore[arg-type]
    )
    assert comments.posted == [("o/r", 1, "進めて")]
    assert dq.enqueued == [("o/r", 1, "進めて")]


def test_handle_create_issue_uses_gh_create_attach_when_supported(tmp_path: Path) -> None:
    labels = FakeLabels()
    created: list[tuple] = []
    dq = _DQ()

    def create_with(repo, title, body, paths):
        created.append((repo, title, body, paths))
        return 9

    result = handle_create_issue(
        "o/r",
        "題",
        "本文",
        "immediate",
        create_issue=lambda *a: pytest.fail("create_issueは使わない"),
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dq,  # type: ignore[arg-type]
        attachments=_saved(tmp_path),
        create_issue_with_attachments=create_with,
        post_comment_with_attachments=lambda *a: pytest.fail("コメントは投稿しない"),
    )
    assert result.issue_number == 9
    assert created == [("o/r", "題", "本文", [str(tmp_path / "x.png")])]
    assert labels.labels_by_issue[9] == {STATUS_IN_PROGRESS}
    [(_, _, message)] = dq.enqueued
    assert message.startswith("本文\n\n" + ATTACHMENT_PATHS_HEADING)


def test_handle_create_issue_falls_back_to_comment_when_create_attach_unsupported(
    tmp_path: Path,
) -> None:
    labels = FakeLabels()
    creator = FakeIssueCreator(start_number=20)
    posted: list[tuple] = []
    dq = _DQ()
    result = handle_create_issue(
        "o/r",
        "題",
        "本文",
        "queued",
        create_issue=creator.create_issue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dq,  # type: ignore[arg-type]
        attachments=_saved(tmp_path),
        create_issue_with_attachments=None,
        post_comment_with_attachments=lambda *a: posted.append(a),
    )
    assert result.dispatched is False
    assert creator.created == [("o/r", "題", "本文")]
    assert posted == [("o/r", 20, "", [str(tmp_path / "x.png")])]
    assert labels.labels_by_issue[20] == {STATUS_TODO}
    assert dq.enqueued == []


# --- HTTP ---


def _server_kwargs(tmp_path: Path, **overrides):
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    dispatch_queue, calls, event = _recording_dispatch_queue()
    posted: list[tuple] = []
    kwargs = dict(
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=FakeComments().post_comment,
        post_comment_with_attachments=lambda *a: posted.append(a),
        uploads_base_dir=tmp_path,
    )
    kwargs.update(overrides)
    return kwargs, calls, event, posted


INSTRUCT = "/api/projects/nosetech/project-a/issues/1/instruct"


def test_server_instruct_with_attachment_saves_posts_and_dispatches(tmp_path: Path) -> None:
    kwargs, calls, event, posted = _server_kwargs(tmp_path)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, _ = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "", "attachments": [_att("s.png", PNG)]},
        )
        assert status == 200
        [(repo, n, body, paths)] = posted
        assert (repo, n, body) == ("nosetech/project-a", 1, "")
        assert Path(paths[0]).read_bytes() == PNG
        assert event.wait(timeout=2)
        assert calls[0][2].endswith(f"→ {paths[0]}")
    finally:
        server.shutdown()


def test_server_instruct_rejects_invalid_attachment_with_400(tmp_path: Path) -> None:
    kwargs, calls, _, posted = _server_kwargs(tmp_path)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, body = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "x", "attachments": [_att("a.svg", PNG)]},
        )
        assert status == 400
        assert "対応していない形式" in body["error"]
        assert posted == []
        assert calls == []
    finally:
        server.shutdown()


def test_server_instruct_rejects_attachment_when_gh_too_old(tmp_path: Path) -> None:
    kwargs, _, _, posted = _server_kwargs(tmp_path, attach_supported=False)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, body = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "x", "attachments": [_att("a.png", PNG)]},
        )
        assert status == 400
        assert "v2.99.0" in body["error"]
        # テキストだけの送信は動く
        status, _ = _post(server, INSTRUCT, {"action": "instruct", "message": "x"})
        assert status == 200
    finally:
        server.shutdown()


def test_server_instruct_removes_files_when_posting_fails(tmp_path: Path) -> None:
    def fail(*a):
        raise subprocess.CalledProcessError(1, ["gh"])

    kwargs, _, _, _ = _server_kwargs(tmp_path, post_comment_with_attachments=fail)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, _ = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "x", "attachments": [_att("a.png", PNG)]},
        )
        assert status == 502
        assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
    finally:
        server.shutdown()


def test_server_create_issue_queued_removes_files_after_posting(tmp_path: Path) -> None:
    created: list[tuple] = []

    def create_with(repo, title, body, paths):
        created.append((repo, title, body, [Path(p).read_bytes() for p in paths]))
        return 30

    kwargs, _, _, _ = _server_kwargs(
        tmp_path, create_issue_with_attachments=create_with, get_labels=lambda r, n: set()
    )
    kwargs["add_label"] = lambda *a: None
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, body = _post(
            server,
            "/api/projects/nosetech/project-a/issues",
            {
                "title": "t",
                "prompt": "p",
                "dispatch": "queued",
                "attachments": [_att("r.webm", WEBM)],
            },
        )
        assert status == 201
        assert body["issue_number"] == 30
        assert created == [("nosetech/project-a", "t", "p", [WEBM])]
        assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
    finally:
        server.shutdown()


def test_server_rejects_oversized_request_with_413(tmp_path: Path, monkeypatch) -> None:
    import orchestrator.server as server_module

    monkeypatch.setattr(server_module, "MAX_ATTACH_REQUEST_BYTES", 100)
    kwargs, _, _, _ = _server_kwargs(tmp_path)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, _ = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "x" * 200},
        )
        assert status == 413
    finally:
        server.shutdown()


def test_server_read_only_rejects_attachment_post(tmp_path: Path) -> None:
    kwargs, _, _, posted = _server_kwargs(tmp_path, read_only=True)
    server, _ = _run_server(StateStore(), **kwargs)
    try:
        status, _ = _post(
            server,
            INSTRUCT,
            {"action": "instruct", "message": "x", "attachments": [_att("a.png", PNG)]},
        )
        assert status == 403
        assert posted == []
    finally:
        server.shutdown()


def test_dispatch_fn_removes_attachments_after_run_even_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    import orchestrator.main as main_module
    from orchestrator.media_uploads import UPLOADS_DIR_ENV

    monkeypatch.setenv(UPLOADS_DIR_ENV, str(tmp_path))
    saved = save_attachments("o/r", "1", decode_attachments([_att("a.png", PNG)]))
    message = append_attachment_paths("x", saved)
    seen: list[bool] = []

    def fake_run(project, issue_number, msg, **kwargs):
        seen.append(saved[0].path.exists())  # 実行中はファイルが残っている
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "run_agent_runner", fake_run)
    project = PROJECT_A
    dispatch_fn = main_module._make_dispatch_fn([project], 7, 1.0, [])
    with pytest.raises(RuntimeError):
        dispatch_fn(project.repo, 1, message)
    assert seen == [True]
    assert not saved[0].path.exists()
