"""orchestrator.agent_runner の単体テスト。

docs/basic-design.md 3章（Agent Runner連携設計）の起動パラメータ・ログ収集・
異常終了時の扱いを、フェイクのsubprocess/gh呼び出しで検証する。
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.agent_runner import build_claude_command, run_agent_runner
from orchestrator.config import Project
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)

FIXED_NOW = lambda: datetime(2026, 8, 4, 1, 2, 3, tzinfo=UTC)  # noqa: E731
FIXED_UUID = lambda: "11111111-1111-1111-1111-111111111111"  # noqa: E731


class FakeLabels:
    def __init__(self, initial: set[str]) -> None:
        self.labels = set(initial)

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        return set(self.labels)

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels.add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels.discard(label)


class FakeComments:
    def __init__(self) -> None:
        self.posted: list[tuple[str, int, str]] = []

    def post_comment(self, repo: str, issue_number: int, body: str) -> None:
        self.posted.append((repo, issue_number, body))


class FakeRun:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append({"cmd": cmd, **kwargs})
        return subprocess.CompletedProcess(
            args=cmd, returncode=self.returncode, stdout=self.stdout, stderr=self.stderr
        )


class FakePersistSessionId:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, repo: str, session_id: str) -> None:
        self.calls.append((repo, session_id))


def test_build_claude_command_new_session_uses_session_id_flag() -> None:
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    assert command == [
        "claude",
        "-p",
        "hello",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--chrome",
        "--append-system-prompt",
        command[8],
        "--session-id",
        "new-id",
    ]


def test_build_claude_command_resume_uses_resume_flag() -> None:
    command = build_claude_command(
        "hello", session_id="existing-id", resume=True, repo="nosetech/project-a", issue_number=12
    )

    assert command == [
        "claude",
        "-p",
        "hello",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--chrome",
        "--append-system-prompt",
        command[8],
        "--resume",
        "existing-id",
    ]


def test_build_claude_command_appends_label_self_management_instruction() -> None:
    """issue #33の再発防止テスト。

    PR作成後にstatus:in-reviewへ自己付与するようAgent Runnerに指示されていな
    かったため、issueがstatus:in-progressのまま宙に浮いた。system promptで
    毎回明示的に指示することを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "nosetech/project-a#12" in instruction
    assert STATUS_IN_REVIEW in instruction
    assert STATUS_NEEDS_HUMAN_DECISION in instruction
    assert STATUS_IN_PROGRESS in instruction
    assert "gh issue edit 12 --repo nosetech/project-a" in instruction


def test_build_claude_command_enables_chrome_integration() -> None:
    """issue #33の再発防止テスト（続報）。

    AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTIONでブラウザ操作ツールの利用
    を指示しても、`-p`（非対話モード）ではClaude in Chrome連携がデフォルト
    無効なため実際には使えなかった。`--chrome`で明示的に有効化する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    assert "--chrome" in command


def test_build_claude_command_appends_design_verification_instruction() -> None:
    """issue #33の再発防止テスト。

    ダッシュボードのUI実装がClaude Designの配色・アイコンを反映できていな
    かった。ブラウザ操作ツールで実際のデザインを確認するよう毎回明示的に
    指示することを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "claude.ai/design" in instruction
    assert "mcp__claude-in-chrome__" in instruction


def test_run_agent_runner_missing_worktree_fails_without_running_subprocess(tmp_path: Path) -> None:
    project = Project(repo="nosetech/project-a", worktree_path=str(tmp_path / "does-not-exist"))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun()

    result = run_agent_runner(
        project,
        1,
        "実装して",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        now=FIXED_NOW,
    )

    assert result.success is False
    assert result.exit_code == -1
    assert run.calls == []
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert len(comments.posted) == 1
    assert "worktreeが見つかりません" in comments.posted[0][2]
    assert result.log_path.exists()
    assert "worktreeが見つかりません" in result.log_path.read_text(encoding="utf-8")


def test_run_agent_runner_first_dispatch_generates_and_persists_session_id(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree), session_id=None)
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun(stdout='{"result": "実装しました"}', returncode=0)
    persist = FakePersistSessionId()

    result = run_agent_runner(
        project,
        1,
        "実装して",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        persist_session_id_fn=persist,
        now=FIXED_NOW,
        new_uuid=FIXED_UUID,
    )

    assert result.session_id == FIXED_UUID()
    assert "--session-id" in run.calls[0]["cmd"]
    assert "--resume" not in run.calls[0]["cmd"]
    assert run.calls[0]["cwd"] == str(worktree)
    assert project.session_id == FIXED_UUID()
    assert persist.calls == [("nosetech/project-a", FIXED_UUID())]
    assert result.success is True
    assert comments.posted == [("nosetech/project-a", 1, "Agent Runner実行結果:\n実装しました")]


def test_run_agent_runner_resumes_existing_session_without_persisting(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(
        repo="nosetech/project-a", worktree_path=str(worktree), session_id="existing-id"
    )
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun(stdout='{"result": "続きをやりました"}', returncode=0)
    persist = FakePersistSessionId()

    result = run_agent_runner(
        project,
        2,
        "続けて",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        persist_session_id_fn=persist,
        now=FIXED_NOW,
    )

    assert result.session_id == "existing-id"
    assert "--resume" in run.calls[0]["cmd"]
    assert "--session-id" not in run.calls[0]["cmd"]
    assert persist.calls == []


def test_run_agent_runner_success_falls_back_when_stdout_is_not_json(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(
        repo="nosetech/project-a", worktree_path=str(worktree), session_id="existing-id"
    )
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun(stdout="not json", returncode=0)

    run_agent_runner(
        project,
        1,
        "実装して",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        now=FIXED_NOW,
    )

    assert "実行結果の要約を取得できませんでした" in comments.posted[0][2]


def test_run_agent_runner_failure_posts_error_comment_and_transitions_to_needs_human_decision(
    tmp_path: Path,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(
        repo="nosetech/project-a", worktree_path=str(worktree), session_id="existing-id"
    )
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun(stdout="", stderr="boom", returncode=1)

    result = run_agent_runner(
        project,
        1,
        "実装して",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        now=FIXED_NOW,
    )

    assert result.success is False
    assert result.exit_code == 1
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert "異常終了" in comments.posted[0][2]
    assert "1" in comments.posted[0][2]


def test_run_agent_runner_writes_log_file_with_issue_number_and_output(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(
        repo="nosetech/project-a", worktree_path=str(worktree), session_id="existing-id"
    )
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    run = FakeRun(stdout='{"result": "ok"}', stderr="warn: something", returncode=0)

    result = run_agent_runner(
        project,
        7,
        "実装して",
        run=run,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        now=FIXED_NOW,
    )

    assert result.log_path == tmp_path / "logs" / "nosetech/project-a" / "20260804T010203Z.log"
    content = result.log_path.read_text(encoding="utf-8")
    assert "issue: #7" in content
    assert '{"result": "ok"}' in content
    assert "warn: something" in content
