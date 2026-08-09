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
from orchestrator.session_store import get_session_id, persist_session_id

DEFAULT_LOGS_DIR = REPO_ROOT / "logs"

RunFn = Callable[..., subprocess.CompletedProcess[str]]
NowFn = Callable[[], datetime]
UuidFn = Callable[[], str]
GetSessionIdFn = Callable[[str, int], str | None]
PersistSessionIdFn = Callable[[str, int, str], None]


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
# だけでは色・アイコンの詳細が伝わらないこと。当初はブラウザ操作ツール
# （mcp__claude-in-chrome__*）での目視確認のみを指示していたが、キャンバス上の
# 要素クリックが自動操作から機能しない・プレビューが状態を持つインタラクション
# を再現しない静的スナップショットである等の理由で細部の再現性に限界があった
# ため、DesignSync MCPでの実ソース直接取得を主手段に切り替えた（issue #55・
# PR #57）。DesignSyncの認証（claude.aiログインへのデザインシステムアクセス
# 権限）は、一度`/design-login`等で許可すればmacOSキーチェーン
# （`Claude Code-credentials`）に永続化され、同一ホスト上の以降の`claude`CLI
# 呼び出し（本Agent Runnerを含む）から自動的に利用できるため、Agent Runner
# 自身が実行時に認証操作を行う必要はない（運用開始前にホスト上で一度だけ人間
# が許可しておくことが前提）。
AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION = (
    "ダッシュボード（dashboard/以下）の画面・コンポーネントを実装・修正する場合、"
    "CLAUDE.mdの「画面デザインの実装ルール」に記載されたClaude DesignのURL"
    "（https://claude.ai/design/...）について、まずDesignSync MCPツール"
    "（get_project→list_files→get_file、projectIdはURLの/p/<uuid>部分）でデザインの"
    "実ソース（ProducerDesk.dc.html）を直接取得し、対象コンポーネントのスタイル"
    "オブジェクト定義（色・余白・border-radius・アニメーション等）をそのまま読み取った"
    "うえで実装してください。テキストの設計文書（docs/design-prompt-dashboard.md等）"
    "にはレイアウトの要件しか書かれておらず、色やアイコンの指定はデザインそのものにしか"
    "ありません。DesignSyncが権限不足等で使えない場合はフォールバックしないでください。"
    "プレビュー画面のクリック操作によるコード選択、ズームしての目視推測、"
    "mcp__claude-in-chrome__* でのチャットへの問い合わせは不正確になりうるため代替に"
    "せず、その旨を実行結果に明記してその場で作業を停止し、needs-human-decisionラベルで"
    "人間の確認を仰いでください。DesignSyncで値を取得できた場合、実装後は"
    "mcp__claude-in-chrome__* で実装結果とデザインのプレビューを並べて見た目が一致する"
    "ことを確認してから完了としてください。"
)


# issue #59: コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成といった
# 補助用途に限り、MCP `ollama-client`経由でローカルLLMを併用する（自走タスク本体は
# 引き続きClaude Codeのみを使う。docs/requirements.md 2-5参照）。呼び出すか否か・
# どのモデルを使うかはAgent Runner自身の裁量とするため、タスク種別ごとの推奨モデルを
# system promptで伝える（docs/basic-design.md 4章参照）。
AGENT_RUNNER_LOCAL_LLM_INSTRUCTION = (
    "コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成といった、"
    "コード変更そのものを伴わない補助的な作業では、必要に応じてMCP `ollama-client` "
    "経由でローカルLLM（Ollama）を併用してよいです。以下のタスク種別ごとの推奨モデルを"
    "参考に、呼び出すかどうか・どのモデルを使うかはあなた自身で判断してください"
    "（docs/basic-design.md 4章「モデルルーター設定設計」参照）。\n"
    "- コードレビュー支援: `deepseek-coder-v2:16b`\n"
    "- デバッグ調査の下調べ: `deepseek-coder-v2:16b`\n"
    "- 日本語ドキュメント生成: `gemma2`\n"
    "- 上記以外・速度優先の簡易チェック: `qwen2.5-coder:7b`\n"
    "ただし、コード変更そのもの（自走タスク本体）にはローカルLLMの出力をそのまま "
    "採用せず、必ずあなた自身（Claude Code）が最終的な変更を行ってください"
    "（ローカルLLMはFunction Callingの信頼性に課題があるため。"
    "docs/requirements.md 2-5参照）。"
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
        + "\n\n"
        + AGENT_RUNNER_LOCAL_LLM_INSTRUCTION
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
    get_session_id_fn: GetSessionIdFn = get_session_id,
    persist_session_id_fn: PersistSessionIdFn = persist_session_id,
    now: NowFn = lambda: datetime.now(UTC),
    new_uuid: UuidFn = lambda: str(uuid.uuid4()),
) -> AgentRunResult:
    """Claude Code CLIをワンショット実行し、結果をissueコメント・ログに反映する。

    セッションはissue単位（`get_session_id_fn`/`persist_session_id_fn`が
    `(repo, issue_number)`をキーに管理、[[docs/basic-design.md 3-1]]参照）で
    保持する。プロジェクト単位で1つのセッションを共有すると、あるissueが
    判断待ちで止まっている間に別issueが同じセッションで進行し、後から前者を
    resumeした際に後者issueの文脈を引きずってしまう（issue #32）。
    """
    timestamp = now().strftime("%Y%m%dT%H%M%SZ")
    worktree_path = Path(project.worktree_path)
    existing_session_id = get_session_id_fn(project.repo, issue_number)

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
            session_id=existing_session_id or "",
            success=False,
        )

    resume = existing_session_id is not None
    session_id = existing_session_id or new_uuid()
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
        persist_session_id_fn(project.repo, issue_number, session_id)

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
