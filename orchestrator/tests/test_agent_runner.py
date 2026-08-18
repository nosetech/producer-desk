"""orchestrator.agent_runner の単体テスト。

docs/basic-design.md 3章（Agent Runner連携設計）の起動パラメータ・ログ収集・
異常終了時の扱いを、フェイクのPopen/gh呼び出しで検証する。

issue #49: `claude -p`の出力形式を`--output-format json`（完了後に一括取得）
から`--output-format stream-json --verbose`（NDJSONを逐次出力）へ変更したため、
`subprocess.run`を模倣する`FakeRun`ではなく、行イテレータを持つ
`subprocess.Popen`を模倣する`FakePopen`/`FakePopenFactory`でテストする。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator import agent_runner
from orchestrator.agent_runner import build_claude_command, run_agent_runner
from orchestrator.config import Project
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)
from orchestrator.usage_store import UsageRecord

FIXED_NOW = lambda: datetime(2026, 8, 4, 1, 2, 3, tzinfo=UTC)  # noqa: E731
FIXED_UUID = lambda: "11111111-1111-1111-1111-111111111111"  # noqa: E731


def result_line(payload: dict) -> str:
    """NDJSON出力中の`"type":"result"`イベント1行分を組み立てる。"""
    return json.dumps({"type": "result", **payload}) + "\n"


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


class FakePopen:
    """`subprocess.Popen`の必要最小限（`stdout`の行イテレータ・`wait()`）を模倣する。"""

    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


class FakePopenFactory:
    def __init__(self, lines: list[str] | None = None, returncode: int = 0) -> None:
        self.lines = lines if lines is not None else []
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> FakePopen:
        self.calls.append({"cmd": cmd, **kwargs})
        return FakePopen(self.lines, self.returncode)


class FakePersistSessionId:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    def __call__(self, repo: str, issue_number: int, session_id: str) -> None:
        self.calls.append((repo, issue_number, session_id))


class FakeGetSessionId:
    def __init__(self, sessions: dict[tuple[str, int], str] | None = None) -> None:
        self.sessions = dict(sessions or {})

    def __call__(self, repo: str, issue_number: int) -> str | None:
        return self.sessions.get((repo, issue_number))


class FakeRecordUsage:
    def __init__(self) -> None:
        self.calls: list[list[UsageRecord]] = []

    def __call__(self, records: list[UsageRecord], **kwargs: object) -> None:
        self.calls.append(list(records))


def test_build_claude_command_new_session_uses_session_id_flag() -> None:
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    assert command == [
        "claude",
        "-p",
        "hello",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--chrome",
        "--append-system-prompt",
        command[9],
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
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--chrome",
        "--append-system-prompt",
        command[9],
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


def test_build_claude_command_appends_comment_marker_instruction() -> None:
    """issue #43の再発防止テスト。

    Agent Runnerが`gh issue comment`等でissueに直接コメント投稿する際、
    `BOT_COMMENT_MARKER`を付与し忘れるとcomment_watcherが自分自身の投稿を
    人間からの新規指示と誤検知し、無限に再ディスパッチしてしまう。system
    promptで毎回マーカー付与を明示的に指示することを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert BOT_COMMENT_MARKER in instruction


def test_build_claude_command_instructs_not_to_duplicate_completion_report() -> None:
    """issue #84の再発防止テスト。

    セッション終了時の最終応答は`run_agent_runner`がオーケストレータ側で
    無条件に「Agent Runner実行結果:」としてissueコメント投稿するため、AI
    自身が対応完了時に重ねて完了報告コメントを投稿するとほぼ同内容のコメン
    トが2つ連続で並んでしまう（issue #80・#70・#77で確認）。system promptで
    その旨と、能動的投稿を限定すべき場面を明示的に指示することを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "Agent Runner実行結果:" in instruction
    assert "重ねて完了報告コメントとして投稿する必要はありません" in instruction


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


def test_build_claude_command_appends_local_llm_instruction() -> None:
    """issue #59: 補助用途でのローカルLLM使い分け指示がsystem promptに含まれることを確認する。

    自走タスク本体には使わない旨、タスク種別ごとの推奨モデルがそれぞれ
    system promptに含まれていることを検証する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "deepseek-coder-v2:16b" in instruction
    assert "gemma2" in instruction


def test_build_claude_command_instructs_ollama_bench_for_usage_recording() -> None:
    """issue #107の再発防止テスト。

    MCP `ollama-client`経由の生成呼び出しではOllama REST APIのトークン数・
    処理時間メトリクスが取得できず`config/usage.db`に記録できないため、生成
    本体は`ollama-bench` CLI（`--record`）を使うようsystem promptで明示的に
    指示し、かつ実行対象のrepo/issue番号が埋め込まれることを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "$OLLAMA_BENCH_PATH" in instruction
    assert "--record --repo nosetech/project-a --issue-number 12" in instruction
    assert "mcp__ollama-client__ollama_chat" in instruction
    assert "mcp__ollama-client__ollama_list" in instruction


def test_build_claude_command_appends_pr_issue_reference_instruction() -> None:
    """issue #82の再発防止テスト。

    PR本文で`issue #77で報告された...`のように issue番号の直後に区切り文字なく
    日本語が続く記法だと、GitHubの自動リンク解析がissue参照として認識せず
    cross-referenceイベントが生成されず、レビュー承認時にPRを解決できなかった。
    `Closes #<issue番号>`を独立行として書くようsystem promptで明示することを
    確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    flag_index = command.index("--append-system-prompt")
    instruction = command[flag_index + 1]

    assert "Closes #<issue番号>" in instruction
    assert "issue #82" in instruction
    assert "qwen2.5-coder:7b" in instruction


def test_build_claude_command_uses_stream_json_output_format() -> None:
    """issue #49の再発防止テスト。

    実行時間の長いタスクで完了までログが一切伸びない問題への対応として、
    `--output-format json`（完了後に一括出力）ではなく`--output-format
    stream-json --verbose`（NDJSONを逐次出力）を使うことを確認する。
    """
    command = build_claude_command(
        "hello", session_id="new-id", resume=False, repo="nosetech/project-a", issue_number=12
    )

    output_format_index = command.index("--output-format")
    assert command[output_format_index + 1] == "stream-json"
    assert "--verbose" in command
    assert "json" not in command


def test_run_agent_runner_missing_worktree_fails_without_running_subprocess(tmp_path: Path) -> None:
    project = Project(repo="nosetech/project-a", worktree_path=str(tmp_path / "does-not-exist"))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory()
    get_session = FakeGetSessionId()

    result = run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert result.success is False
    assert result.exit_code == -1
    assert popen.calls == []
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert len(comments.posted) == 1
    assert "worktreeが見つかりません" in comments.posted[0][2]
    assert result.log_path.exists()
    assert "worktreeが見つかりません" in result.log_path.read_text(encoding="utf-8")


def test_run_agent_runner_first_dispatch_generates_and_persists_session_id(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "実装しました"})], returncode=0)
    get_session = FakeGetSessionId()
    persist = FakePersistSessionId()

    result = run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        persist_session_id_fn=persist,
        now=FIXED_NOW,
        new_uuid=FIXED_UUID,
    )

    assert result.session_id == FIXED_UUID()
    assert "--session-id" in popen.calls[0]["cmd"]
    assert "--resume" not in popen.calls[0]["cmd"]
    assert popen.calls[0]["cwd"] == str(worktree)
    assert persist.calls == [("nosetech/project-a", 1, FIXED_UUID())]
    assert result.success is True
    assert comments.posted == [("nosetech/project-a", 1, "Agent Runner実行結果:\n実装しました")]


def test_resolve_ollama_bench_path_prefers_console_script_next_to_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """issue #107の再発防止テスト。

    `ollama-bench`はオーケストレータ自身のvenvにのみインストールされたコンソール
    スクリプトだが、`claude -p`は別プロジェクトのworktreeをcwdに起動される。バレの
    コマンド名のままではPATH解決できずcommand-not-foundで失敗し利用量が記録され
    ない。`sys.executable`と同じディレクトリに`ollama-bench`が実在する場合、その
    絶対パスをそのまま返すことを確認する（`.resolve()`でsymlinkを辿ると、Homebrew
    管理の実体側ディレクトリを指してしまい存在しなくなるため使わない）。
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ollama-bench").write_text("#!/bin/sh\n")
    monkeypatch.setattr(agent_runner.sys, "executable", str(bin_dir / "python"))

    assert agent_runner._resolve_ollama_bench_path() == str(bin_dir / "ollama-bench")


def test_resolve_ollama_bench_path_falls_back_to_which(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sys.executable`の隣に無い場合、PATH上の`ollama-bench`（`shutil.which`）を使う。"""
    monkeypatch.setattr(agent_runner.sys, "executable", str(tmp_path / "no-such-dir" / "python"))
    monkeypatch.setattr(agent_runner.shutil, "which", lambda name: "/usr/local/bin/ollama-bench")

    assert agent_runner._resolve_ollama_bench_path() == "/usr/local/bin/ollama-bench"


def test_resolve_ollama_bench_path_falls_back_to_bare_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """どちらでも見つからない場合はバレのコマンド名にフォールバックする。"""
    monkeypatch.setattr(agent_runner.sys, "executable", str(tmp_path / "no-such-dir" / "python"))
    monkeypatch.setattr(agent_runner.shutil, "which", lambda name: None)

    assert agent_runner._resolve_ollama_bench_path() == "ollama-bench"


def test_run_agent_runner_passes_resolved_ollama_bench_path_via_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """issue #107の再発防止テスト。

    system prompt本文に解決済みの絶対パスを埋め込み複数のBashツール呼び出しに
    またがって書き写させる方式は、長いパスの写し間違いによる「command not
    found」を誘発しやすい。代わりに`$OLLAMA_BENCH_PATH`環境変数として子プロ
    セスに渡し、Agent Runnerには短い参照だけを使わせることを確認する。
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "実装しました"})], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})
    monkeypatch.setattr(
        agent_runner,
        "_resolve_ollama_bench_path",
        lambda: "/opt/orchestrator/.venv/bin/ollama-bench",
    )

    run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    call_kwargs = popen.calls[0]
    assert call_kwargs["env"]["OLLAMA_BENCH_PATH"] == "/opt/orchestrator/.venv/bin/ollama-bench"
    # オーケストレータ自身のPATH等、既存の環境変数はそのまま引き継がれる。
    assert call_kwargs["env"]["PATH"] == os.environ["PATH"]


def test_resolve_ollama_bench_path_logs_warning_when_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`sys.executable`隣接・PATHのいずれでも見つからない場合、診断用の警告ログを残す。

    サイレントにバレのコマンド名へフォールバックすると、`$OLLAMA_BENCH_PATH`が
    PATH解決できず利用量が記録されない不具合が再発しても運用側から検知できない。
    """
    monkeypatch.setattr(agent_runner.sys, "executable", str(tmp_path / "no-such-dir" / "python"))
    monkeypatch.setattr(agent_runner.shutil, "which", lambda name: None)

    with caplog.at_level("WARNING", logger="orchestrator.agent_runner"):
        result = agent_runner._resolve_ollama_bench_path()

    assert result == "ollama-bench"
    assert any("ollama-bench" in record.message for record in caplog.records)


def test_run_agent_runner_resumes_existing_session_without_persisting(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "続きをやりました"})], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 2): "existing-id"})
    persist = FakePersistSessionId()

    result = run_agent_runner(
        project,
        2,
        "続けて",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        persist_session_id_fn=persist,
        now=FIXED_NOW,
    )

    assert result.session_id == "existing-id"
    assert "--resume" in popen.calls[0]["cmd"]
    assert "--session-id" not in popen.calls[0]["cmd"]
    assert persist.calls == []


def test_run_agent_runner_uses_independent_sessions_per_issue(tmp_path: Path) -> None:
    """issue #32の再発防止テスト。

    セッションがプロジェクト単位で1つだけだと、あるissueが判断待ちで止まって
    いる間に別issueが同じセッションで進行し、後から前者をresumeした際に後者
    issueの文脈を引きずってしまう。issue番号ごとに独立したセッションを解決
    することを確認する。
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "ok"})], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 38): "session-for-38"})
    persist = FakePersistSessionId()

    run_agent_runner(
        project,
        32,
        "作業を再開してください",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        persist_session_id_fn=persist,
        now=FIXED_NOW,
        new_uuid=FIXED_UUID,
    )

    # issue #38用のセッションではなく、issue #32用に新規セッションが作られる
    assert "--session-id" in popen.calls[0]["cmd"]
    assert "--resume" not in popen.calls[0]["cmd"]
    assert "session-for-38" not in popen.calls[0]["cmd"]
    assert persist.calls == [("nosetech/project-a", 32, FIXED_UUID())]


def test_run_agent_runner_success_falls_back_when_stdout_is_not_json(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=["not json\n"], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})

    run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert "実行結果の要約を取得できませんでした" in comments.posted[0][2]


def test_run_agent_runner_failure_posts_error_comment_and_transitions_to_needs_human_decision(
    tmp_path: Path,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=["boom\n"], returncode=1)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})

    result = run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert result.success is False
    assert result.exit_code == 1
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert "異常終了" in comments.posted[0][2]
    assert "1" in comments.posted[0][2]


def test_run_agent_runner_success_without_label_self_transition_falls_back_to_needs_human_decision(
    tmp_path: Path,
) -> None:
    """issue #78の再発防止テスト。

    プロセスは正常終了（exit 0）したが、Agent Runnerがラベルの自己遷移
    （AGENT_RUNNER_LABEL_INSTRUCTION）を怠り status:in-progress のまま
    変化しなかった場合、オーケストレータ側の決定的フォールバックで
    needs-human-decision へ強制的に遷移させることを確認する（issue #70で
    実際に発生した「判断待ちが宙に浮く」不具合の再発防止）。
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    popen = FakePopenFactory(
        lines=[result_line({"result": "このままpushしてPRを作成してよろしいですか？"})],
        returncode=0,
    )
    get_session = FakeGetSessionId({("nosetech/project-a", 70): "existing-id"})

    result = run_agent_runner(
        project,
        70,
        "作業を進めてください",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert result.success is True
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}


def test_run_agent_runner_success_with_self_transition_does_not_double_transition(
    tmp_path: Path,
) -> None:
    """Agent Runnerが自らstatus:in-reviewへ正しく自己遷移済みの場合、

    オーケストレータ側のフォールバックが余計な二重遷移を起こさないことを
    確認する（issue #78）。
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "PRを作成しました"})], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 71): "existing-id"})

    result = run_agent_runner(
        project,
        71,
        "作業を進めてください",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert result.success is True
    assert labels.labels == {STATUS_IN_REVIEW}


def test_run_agent_runner_writes_log_file_incrementally_with_issue_number_and_output(
    tmp_path: Path,
) -> None:
    """issue #49の再発防止テスト。

    ログファイルは実行開始時点で作成され、NDJSON出力を1行読むたびに追記
    される（プロセス終了後の一括書き出しではない）ことを、フェイクの
    `Popen.stdout`イテレータから供給される各行がログファイルへ反映されて
    いることで確認する。
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(
        lines=[result_line({"result": "ok"}), "warn: something\n"], returncode=0
    )
    get_session = FakeGetSessionId({("nosetech/project-a", 7): "existing-id"})

    result = run_agent_runner(
        project,
        7,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    assert result.log_path == tmp_path / "logs" / "nosetech/project-a" / "20260804T010203Z.log"
    content = result.log_path.read_text(encoding="utf-8")
    assert "issue: #7" in content
    assert '"result": "ok"' in content
    assert "warn: something" in content


def test_run_agent_runner_passes_stdout_and_merged_stderr_to_popen(tmp_path: Path) -> None:
    """issue #49: `Popen`をPIPE/STDOUTで起動し、標準エラーの取りこぼしを防ぐことを確認する。"""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=[result_line({"result": "ok"})], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 7): "existing-id"})

    run_agent_runner(
        project,
        7,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        now=FIXED_NOW,
    )

    call_kwargs = popen.calls[0]
    assert call_kwargs["stdout"] == subprocess.PIPE
    assert call_kwargs["stderr"] == subprocess.STDOUT
    assert call_kwargs["text"] is True


def test_run_agent_runner_records_usage_per_model_from_model_usage_payload(
    tmp_path: Path,
) -> None:
    """issue #60: `modelUsage`を破棄せず、モデル別の利用量として記録することを確認する。"""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    payload_line = result_line(
        {
            "result": "実装しました",
            "is_error": False,
            "total_cost_usd": 0.12,
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "cacheCreationInputTokens": 5,
                    "cacheReadInputTokens": 2,
                    "costUSD": 0.12,
                }
            },
        }
    )
    popen = FakePopenFactory(lines=[payload_line], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})
    record_usage_fn = FakeRecordUsage()

    run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        record_usage_fn=record_usage_fn,
        now=FIXED_NOW,
    )

    assert len(record_usage_fn.calls) == 1
    [records] = record_usage_fn.calls
    assert records == [
        UsageRecord(
            repo="nosetech/project-a",
            issue_number=1,
            model="claude-sonnet-5",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=5,
            cache_read_input_tokens=2,
            total_cost_usd=0.12,
            is_error=False,
            api_error_status=None,
            error_message=None,
            limit_reset_text=None,
        )
    ]


def test_run_agent_runner_records_limit_reached_with_parsed_reset_text(tmp_path: Path) -> None:
    """issue #60: 429到達時、`result`の自由文から解除予定時刻をパースして記録することを確認する。"""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    payload_line = result_line(
        {
            "is_error": True,
            "api_error_status": 429,
            "result": "You've hit your session limit · resets 1pm (Asia/Tokyo)",
        }
    )
    popen = FakePopenFactory(lines=[payload_line], returncode=1)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})
    record_usage_fn = FakeRecordUsage()

    run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        record_usage_fn=record_usage_fn,
        now=FIXED_NOW,
    )

    assert len(record_usage_fn.calls) == 1
    [records] = record_usage_fn.calls
    assert records == [
        UsageRecord(
            repo="nosetech/project-a",
            issue_number=1,
            model="unknown",
            input_tokens=0,
            output_tokens=0,
            is_error=True,
            api_error_status=429,
            error_message="You've hit your session limit · resets 1pm (Asia/Tokyo)",
            limit_reset_text="resets 1pm (Asia/Tokyo)",
        )
    ]


def test_run_agent_runner_does_not_record_usage_when_stdout_is_not_json(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = Project(repo="nosetech/project-a", worktree_path=str(worktree))
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    popen = FakePopenFactory(lines=["not json\n"], returncode=0)
    get_session = FakeGetSessionId({("nosetech/project-a", 1): "existing-id"})
    record_usage_fn = FakeRecordUsage()

    run_agent_runner(
        project,
        1,
        "実装して",
        popen=popen,
        post_comment=comments.post_comment,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        logs_dir=tmp_path / "logs",
        get_session_id_fn=get_session,
        record_usage_fn=record_usage_fn,
        now=FIXED_NOW,
    )

    assert record_usage_fn.calls == []
