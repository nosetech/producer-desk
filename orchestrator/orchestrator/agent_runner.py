"""Agent Runner連携: Claude Code CLIのワンショット起動・監視・ログ収集。

仕様: docs/basic-design.md 3章（Agent Runner連携設計）
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.config import REPO_ROOT, Project
from orchestrator.github_client import PostCommentFn
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    gh_add_label,
    gh_get_labels,
    gh_remove_label,
    transition_label,
)
from orchestrator.session_store import persist_session_id

DEFAULT_LOGS_DIR = REPO_ROOT / "logs"

RunFn = Callable[..., subprocess.CompletedProcess[str]]
NowFn = Callable[[], datetime]
UuidFn = Callable[[], str]
PersistSessionIdFn = Callable[[str, str], None]


@dataclass
class AgentRunResult:
    repo: str
    issue_number: int
    exit_code: int
    log_path: Path
    session_id: str
    success: bool


# 状態遷移のうち、正常終了時のstatus:in-review・needs-human-decisionへの遷移は
# Agent Runner自身が`gh`コマンドで自己付与する設計（docs/basic-design.md 1章）。
# しかし実際にはこの指示がプロンプトに含まれていないと実行されないことがあり
# （issue #33: PR作成後もstatus:in-progressのままになり判断待ちが宙に浮いた）、
# `--append-system-prompt`で毎回明示的に指示することで確実性を上げる。
AGENT_RUNNER_LABEL_INSTRUCTION = (
    "あなたはproducer-deskオーケストレータからディスパッチされたAgent Runnerとして、"
    "GitHub issue {repo}#{issue_number} に取り組んでいます。"
    "以下の状態ラベル遷移は、オーケストレータ側では自動的に行われないため、"
    "該当する状況になったらあなた自身がghコマンドで実行してください"
    "（docs/basic-design.md 1章「データモデル・状態遷移設計」参照）。\n"
    "- 人間の判断が必要だと自ら判断した場合: "
    f"`gh issue edit {{issue_number}} --repo {{repo}} "
    f"--add-label {STATUS_NEEDS_HUMAN_DECISION} --remove-label {STATUS_IN_PROGRESS}`\n"
    "- プルリクエストを作成した場合: "
    f"`gh issue edit {{issue_number}} --repo {{repo}} "
    f"--add-label {STATUS_IN_REVIEW} --remove-label {STATUS_IN_PROGRESS}`\n"
    "状態ラベル（status:todo / status:in-progress / needs-human-decision / "
    "status:in-review）は常にいずれか1つのみが付与されている状態を保ってください。"
)

# issue #33の再発防止: ダッシュボードのUI実装がClaude Designの見た目（配色・
# アイコン等）を反映できていなかった。原因は、CLAUDE.mdが「正」とするデザイン
# URL（claude.ai/design/...）が認証必須でWebFetchでは403になり、テキスト指示
# だけでは色・アイコンの詳細が伝わらないこと。ブラウザ操作ツール
# （mcp__claude-in-chrome__*、claude.aiにログイン済みのChromeとペアリング済み
# 前提）で実際にデザインを開いて確認するよう毎回明示的に指示する。
AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION = (
    "ダッシュボード（dashboard/以下）の画面・コンポーネントを実装・修正する場合、"
    "CLAUDE.mdの「画面デザインの実装ルール」に記載されたClaude DesignのURL"
    "（https://claude.ai/design/...）を必ずブラウザ操作ツール"
    "（mcp__claude-in-chrome__* ツール）で開き、対象コンポーネントの配色・アイコン・"
    "余白・状態変化などの視覚的詳細を実際に確認したうえで実装してください。"
    "テキストの設計文書（docs/design-prompt-dashboard.md等）にはレイアウトの要件"
    "しか書かれておらず、色やアイコンの指定はデザインそのものにしかありません。"
    "実装後は同じブラウザツールで実装結果とデザインを見比べ、細部が一致することを"
    "確認してから完了としてください。ブラウザ操作ツールが利用できない場合（Chrome"
    "が起動していない、claude.aiにログインしていない等）は、その旨を実行結果に明記し、"
    "人間の確認を仰いでください。"
)


def build_claude_command(
    message: str, *, session_id: str, resume: bool, repo: str, issue_number: int
) -> list[str]:
    """docs/basic-design.md 3-1の起動パラメータに従いコマンドを組み立てる。

    worktreeディレクトリの指定は本関数の責務外（呼び出し側でsubprocessのcwdに渡す）。
    """
    system_prompt = (
        AGENT_RUNNER_LABEL_INSTRUCTION.format(repo=repo, issue_number=issue_number)
        + "\n\n"
        + AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION
    )
    command = [
        "claude",
        "-p",
        message,
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        # `-p`（非対話モード）ではClaude in Chrome連携がデフォルト無効なため、
        # AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTIONでブラウザ操作ツールの
        # 利用を指示するだけでは実際には使えない。明示的に有効化する。
        "--chrome",
        "--append-system-prompt",
        system_prompt,
    ]
    if resume:
        command += ["--resume", session_id]
    else:
        command += ["--session-id", session_id]
    return command


def _write_log(
    repo: str, issue_number: int, stdout: str, stderr: str, *, logs_dir: Path, timestamp: str
) -> Path:
    log_dir = logs_dir / repo
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{timestamp}.log"
    content = f"issue: #{issue_number}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    log_path.write_text(content, encoding="utf-8")
    return log_path


def _extract_summary(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    return result if isinstance(result, str) else None


def run_agent_runner(
    project: Project,
    issue_number: int,
    message: str,
    *,
    run: RunFn = subprocess.run,
    post_comment: PostCommentFn = gh_post_comment,
    get_labels: GetLabelsFn = gh_get_labels,
    add_label: AddLabelFn = gh_add_label,
    remove_label: RemoveLabelFn = gh_remove_label,
    logs_dir: Path = DEFAULT_LOGS_DIR,
    persist_session_id_fn: PersistSessionIdFn = persist_session_id,
    now: NowFn = lambda: datetime.now(UTC),
    new_uuid: UuidFn = lambda: str(uuid.uuid4()),
) -> AgentRunResult:
    """Claude Code CLIをワンショット実行し、結果をissueコメント・ログに反映する。"""
    timestamp = now().strftime("%Y%m%dT%H%M%SZ")
    worktree_path = Path(project.worktree_path)

    if not worktree_path.is_dir():
        error_message = f"worktreeが見つかりません: {project.worktree_path}"
        post_comment(
            project.repo, issue_number, f":warning: Agent Runner起動エラー\n{error_message}"
        )
        transition_label(
            project.repo,
            issue_number,
            STATUS_NEEDS_HUMAN_DECISION,
            get_labels=get_labels,
            add_label=add_label,
            remove_label=remove_label,
        )
        log_path = _write_log(
            project.repo, issue_number, "", error_message, logs_dir=logs_dir, timestamp=timestamp
        )
        return AgentRunResult(
            repo=project.repo,
            issue_number=issue_number,
            exit_code=-1,
            log_path=log_path,
            session_id=project.session_id or "",
            success=False,
        )

    resume = project.session_id is not None
    session_id = project.session_id or new_uuid()
    command = build_claude_command(
        message,
        session_id=session_id,
        resume=resume,
        repo=project.repo,
        issue_number=issue_number,
    )

    result = run(command, cwd=str(worktree_path), capture_output=True, text=True)

    log_path = _write_log(
        project.repo,
        issue_number,
        result.stdout,
        result.stderr,
        logs_dir=logs_dir,
        timestamp=timestamp,
    )

    if not resume:
        project.session_id = session_id
        persist_session_id_fn(project.repo, session_id)

    success = result.returncode == 0

    if success:
        summary = (
            _extract_summary(result.stdout)
            or "(実行結果の要約を取得できませんでした。ログを参照してください。)"
        )
        post_comment(project.repo, issue_number, f"Agent Runner実行結果:\n{summary}")
    else:
        error_comment = (
            f":warning: Agent Runnerが異常終了しました"
            f"（終了コード: {result.returncode}）。ログ: {log_path}"
        )
        post_comment(project.repo, issue_number, error_comment)
        transition_label(
            project.repo,
            issue_number,
            STATUS_NEEDS_HUMAN_DECISION,
            get_labels=get_labels,
            add_label=add_label,
            remove_label=remove_label,
        )

    return AgentRunResult(
        repo=project.repo,
        issue_number=issue_number,
        exit_code=result.returncode,
        log_path=log_path,
        session_id=session_id,
        success=success,
    )
