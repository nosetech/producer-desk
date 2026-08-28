"""Agent Runner連携: Claude Code CLIのワンショット起動・監視・ログ収集。

仕様: docs/basic-design.md 3章（Agent Runner連携設計）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.config import DEFAULT_LOG_RETENTION_DAYS, REPO_ROOT, Project
from orchestrator.github_client import (
    BOT_COMMENT_MARKER,
    AppendPrIssueReferenceFn,
    FindOpenPrByBranchFn,
    GetCurrentBranchFn,
    PostCommentFn,
    ResolvePrNumberFn,
)
from orchestrator.github_client import append_pr_issue_reference as gh_append_pr_issue_reference
from orchestrator.github_client import find_open_pr_by_branch as gh_find_open_pr_by_branch
from orchestrator.github_client import get_current_branch as gh_get_current_branch
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.github_client import resolve_pr_number as gh_resolve_pr_number
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
from orchestrator.timezone import JST
from orchestrator.usage_store import (
    RecordUsageFn,
    UsageRecord,
    parse_limit_reset_text,
)
from orchestrator.usage_store import (
    record_usage as store_record_usage,
)

logger = logging.getLogger(__name__)

DEFAULT_LOGS_DIR = REPO_ROOT / "logs"

PopenFn = Callable[..., subprocess.Popen]
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
#
# issue #104: 当初「プルリクエストを作成した場合」を条件にしていたため、PR作成
# 直後に即座にstatus:in-reviewへ遷移してしまい、fix-github-issueスキルの後続
# ステップ（CI完了待ち・code-reviewerサブエージェントによるレビュー・レビュー
# 結果のPRコメント投稿）が完了する前にダッシュボードのレビュー待ち一覧（判定は
# ラベルのみを見る）にカードが出てしまう不具合があった。ラベル遷移は「PR作成」
# ではなく「そのissueについて自分がこのセッション内で行う一連の作業が完了した
# 時点」に紐付ける。
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
    "  ただし、PR作成はこのコマンドを実行してよいタイミングの下限に過ぎません。"
    "CI完了待ち・コードレビューの実施・レビュー結果のPRへのコメント投稿など、"
    "そのissueについてこのセッション内で自分が続けて行う後続作業がある場合は、"
    "それらを全て終えるまでこのラベル遷移を実行しないでください。PR作成直後に"
    "即座に実行すると、まだレビュー結果が投稿されていないのにダッシュボードの"
    "レビュー待ち一覧に表示されてしまいます（ラベルの有無だけで判定するため）。\n"
    "  なお、CI完了待ちのように単に時間経過を要するだけの状況は、それ自体が"
    "needs-human-decisionへ遷移すべき理由にはなりません。CIが実行中"
    "（PENDING/IN_PROGRESS）の間はneeds-human-decisionを使わず、"
    f"`gh pr view <PR番号> --repo {{repo}} --json statusCheckRollup` をBashツールで"
    "sleepを挟みながら繰り返し確認するポーリングにより、このセッション内で"
    "status:in-progressのまま待機を継続し、CI完了後に後続作業へ進んでください。\n"
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
# 補助用途に限り、ローカルLLMを併用する（自走タスク本体は引き続きClaude Codeのみを
# 使う。docs/requirements.md 2-5参照）。呼び出すか否か・どのモデルを使うかはAgent
# Runner自身の裁量とするため、タスク種別ごとの推奨モデルをsystem promptで伝える
# （docs/basic-design.md 4章参照）。
#
# issue #107: MCP `ollama-client`（サードパーティ`ollama-mcp`パッケージ）の
# `ollama_chat`ツールはOllama REST APIレスポンスから`content`のみを取り出して返し、
# `prompt_eval_count`/`eval_count`/`total_duration`等のメトリクスを破棄するため、
# MCP経由の呼び出しでは利用量を`config/usage.db`に記録できない（issue #60の調査で
# 判明、`ollama_bench.py`を手動ベンチマーク専用ツールとして追加していた）。生成本体
# の呼び出しはOllama REST APIを直接叩き利用量を記録する`ollama-bench` CLIに一本化
# し、本番経路でも利用量がダッシュボードに反映されるようにする。モデルの利用可否
# 確認（メトリクス不要）はMCP `mcp__ollama-client__ollama_list`/`ollama_ps`のままで
# よい。
#
# `ollama-bench`はオーケストレータ自身のvenvにのみインストールされたコンソール
# スクリプトで、Agent Runnerが担当するプロジェクトのworktree（producer-desk自身
# とは別リポジトリのことが多い）のPATHには存在しない。解決済みの絶対パスを
# system prompt本文に直接埋め込みBashツール呼び出しのたびに再現させる案は、長い
# パスをLLMが複数回のツール呼び出しにまたがって書き写す必要があり、写し間違いで
# 同じ「command not found」に陥りやすい。代わりに`run_agent_runner`が起動する
# 子プロセスの環境変数`OLLAMA_BENCH_PATH`に解決済みパスを設定し（`popen`の`env=`
# 参照）、Agent Runnerには短く安定した`$OLLAMA_BENCH_PATH`という参照だけを
# 覚えさせる。
AGENT_RUNNER_LOCAL_LLM_INSTRUCTION = (
    "コードレビュー支援・デバッグ調査の下調べ・日本語ドキュメント生成といった、"
    "コード変更そのものを伴わない補助的な作業では、必要に応じてローカルLLM"
    "（Ollama）を併用してよいです。以下のタスク種別ごとの推奨モデルを参考に、"
    "呼び出すかどうか・どのモデルを使うかはあなた自身で判断してください"
    "（docs/basic-design.md 4章「モデルルーター設定設計」参照）。\n"
    "- コードレビュー支援: `deepseek-coder-v2:16b`\n"
    "- デバッグ調査の下調べ: `deepseek-coder-v2:16b`\n"
    "- 日本語ドキュメント生成: `gemma2`\n"
    "- 上記以外・速度優先の簡易チェック: `qwen2.5-coder:7b`\n"
    "モデルの利用可否確認はMCP `mcp__ollama-client__ollama_list`/`ollama_ps`で構い"
    "ませんが、実際に生成させる呼び出しは必ず環境変数`$OLLAMA_BENCH_PATH`が指す"
    "`ollama-bench`コマンド（Bashツール）経由で行い、`--record --repo {repo} "
    "--issue-number {issue_number}`を付与してください。あなたが作業している"
    "プロジェクトのworktreeにはこのコマンドがPATH解決できないため、バレの"
    "コマンド名`ollama-bench`ではなく必ず`$OLLAMA_BENCH_PATH`経由で呼び出して"
    "ください。プロンプトは一旦ファイルに書き出してから渡しますが、他プロジェクトの"
    "並行実行と衝突しないよう`mktemp`等で毎回一意な一時ファイルパスを生成してくだ"
    "さい（固定パス`/tmp/prompt.txt`等の使い回しは避ける）。例: "
    '`PROMPT_FILE=$(mktemp); "$OLLAMA_BENCH_PATH" deepseek-coder-v2:16b '
    '"$PROMPT_FILE" --system "..." --record --repo {repo} '
    "--issue-number {issue_number}`。MCP `mcp__ollama-client__ollama_chat`は"
    "Ollama REST APIのトークン数・処理時間メトリクスを返さず利用量を記録できない"
    "ため、生成呼び出しには使わないでください。\n"
    "ただし、コード変更そのもの（自走タスク本体）にはローカルLLMの出力をそのまま "
    "採用せず、必ずあなた自身（Claude Code）が最終的な変更を行ってください"
    "（ローカルLLMはFunction Callingの信頼性に課題があるため。"
    "docs/requirements.md 2-5参照）。"
)


# issue #43: Agent Runnerが調査結果報告等の目的で`gh issue comment`等を生で
# 叩いてissueにコメントを投稿すると、`github_client.post_comment`が自動付与
# する`BOT_COMMENT_MARKER`が付かない。comment_watcher.py（新規コメント検知）
# は`BOT_COMMENT_MARKER`が本文に無いコメントを人間からの新規指示とみなすため、
# マーカー無しの自己投稿を誤って新規指示と検知し、同一内容を無限に再ディス
# パッチしてしまう（ラベルもneeds-human-decision→status:in-progressに巻き戻る）。
# AGENT_RUNNER_LABEL_INSTRUCTIONと同様、`--append-system-prompt`で毎回明示的に
# マーカー付与を指示する。
#
# issue #84: `run_agent_runner`はセッション終了時、`claude -p`の最終応答
# （`result`）を無条件に「Agent Runner実行結果:」としてissueコメント投稿する
# （本モジュール後方の`post_comment(..., f"Agent Runner実行結果:\n{summary}")`）。
# この投稿経路の存在をAgent Runnerに伝えていなかったため、対応完了時にAI自身が
# 能動的にも完了報告コメントを投稿してしまい、ほぼ同内容のコメントが2つ連続で
# 投稿される重複が発生していた（issue #80・#70・#77で確認）。能動的投稿は
# 「最終応答を待たずに人間へ可視化する価値がある場合」に限定するよう指示する。
AGENT_RUNNER_COMMENT_MARKER_INSTRUCTION = (
    "issueに調査結果・進捗等を報告するため`gh issue comment`や`gh api "
    ".../comments`等でissueコメントを直接投稿する場合、本文の末尾に必ず次の"
    "マーカーを付与してください（本文とマーカーの間は空行で区切る）。\n"
    f"{BOT_COMMENT_MARKER}\n"
    "このマーカーが無いと、オーケストレータのコメント監視処理があなた自身の"
    "投稿を人間からの新規指示と誤認し、同一内容を無限に再ディスパッチしてし"
    "まいます（docs/basic-design.md 2-3「共通仕様」参照）。\n"
    "なお、あなたのセッション終了時の最終応答（このメッセージへの最後の"
    "返信）は、オーケストレータが自動的に「Agent Runner実行結果:」という"
    "見出しを付けてissueコメントに投稿します。そのため、対応が完了した"
    "旨をあなた自身が重ねて完了報告コメントとして投稿する必要はありません"
    "（投稿すると同内容のコメントが2つ連続で並ぶ重複が発生します）。"
    "能動的なissueコメント投稿は、長時間かかる作業の途中経過など、最終応答を"
    "待たずに人間へ可視化する価値がある場合に限定してください。"
)


# issue #82: Agent Runnerが日本語でPR本文を書く際、`issue #77で報告された...`の
# ように issue番号の直後に区切り文字を挟まず日本語が続く形だと、GitHub側の自動
# リンク解析がissue参照として認識せずcross-referenceイベントが生成されない
# （PR #81で発生。resolve_pr_numberはフォールバックを備えたが、そもそも正しい
# 記法で書けば発生しない問題のため、CLAUDE.mdの既存規約を`--append-system-prompt`
# でも重ねて明示する）。
AGENT_RUNNER_PR_ISSUE_REFERENCE_INSTRUCTION = (
    "プルリクエストを作成する場合、本文に対応するissue番号への参照を"
    "`Closes #<issue番号>`という形で、前後を空行で区切った独立した行として必ず"
    "含めてください。issue番号の直後に半角スペース・改行等の区切り文字を挟まず"
    "日本語（「で」「の」「を」等）を続けて書くと、GitHubの自動リンク解析が"
    "issue参照として認識せず、レビュー承認時にPRを自動解決できなくなります"
    "（issue #82）。「issue #77で報告された...」のような書き方は避けてください。"
)


# issue #164: `run_agent_runner`はセッション終了時、`claude -p`の最終応答を
# 無編集で「Agent Runner実行結果:」としてissueコメント投稿する（本モジュール
# 後方の`post_comment(..., f"Agent Runner実行結果:\n{summary}")`、issue #84の
# AGENT_RUNNER_COMMENT_MARKER_INSTRUCTIONで存在自体は伝えていた）。しかし
# 「その最終応答がそのまま人間向け報告になる」ことを踏まえて内容を書くようには
# 指示していなかったため、Monitor/ScheduleWakeupといった内部ツール名や
# ポーリング方式を書き連ねただけの、人間が読んでも次に何をすべきか分からない
# 文面が投稿されていた（issue #161のコメントで発生。PR #163作成・CI成功済み
# だったにもかかわらず、コメントからはレビュー待ちであることが読み取れなかった）。
AGENT_RUNNER_FINAL_MESSAGE_INSTRUCTION = (
    "セッション終了時のあなたの最終応答（このメッセージへの最後の返信）は、"
    "オーケストレータによって編集されることなくそのまま「Agent Runner実行結果:」"
    "という見出しを付けてissueコメントとして人間に投稿されます。この最終応答は"
    "人間向けの状況報告であることを踏まえ、次の点を意識して書いてください。\n"
    "- needs-human-decisionラベルを付与した場合は、最終応答に"
    "「何について・なぜ人間の判断が必要か」と「人間が具体的に何をすればよいか」"
    "（例:「PR #163をレビューし、問題なければマージしてください」"
    "「A案/B案のどちらで進めるか選んでください」）を明記してください。\n"
    "- Monitor/ScheduleWakeupといった内部ツール名や、ポーリングの実装方法など、"
    "作業手順上の実装詳細は人間向け報告に含めないでください。"
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
        + AGENT_RUNNER_COMMENT_MARKER_INSTRUCTION
        + "\n\n"
        + AGENT_RUNNER_DESIGN_VERIFICATION_INSTRUCTION
        + "\n\n"
        + AGENT_RUNNER_LOCAL_LLM_INSTRUCTION.format(repo=repo, issue_number=issue_number)
        + "\n\n"
        + AGENT_RUNNER_PR_ISSUE_REFERENCE_INSTRUCTION
        + "\n\n"
        + AGENT_RUNNER_FINAL_MESSAGE_INSTRUCTION
    )
    command = [
        "claude",
        "-p",
        message,
        "--output-format",
        "stream-json",
        # issue #49: `stream-json`はツール呼び出し・メッセージ単位でNDJSON（1行1JSON）
        # を逐次標準出力に書き出す。`-p`（非対話モード）で`stream-json`を使う場合、
        # CLIは`--verbose`の指定を必須とする。
        "--verbose",
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


# issue #107: `ollama-bench`はオーケストレータ自身のvenv（`orchestrator/.venv`等）
# にのみインストールされたコンソールスクリプトだが、`claude -p`はAgent Runnerが
# 担当するプロジェクトのworktree（producer-desk自身とは別リポジトリのことが多い）を
# cwdに起動される。オーケストレータプロセスのPATHをそのまま継承させただけでは
# `ollama-bench`がPATH解決できず、AGENT_RUNNER_LOCAL_LLM_INSTRUCTIONの指示が
# 「command not found」で失敗し利用量が一切記録されない。解決結果は
# `run_agent_runner`が子プロセスの環境変数`OLLAMA_BENCH_PATH`に設定する
# （system promptへの埋め込みではなく環境変数にする理由は同定数の直前コメント参照）。
#
# 子プロセスのPATH自体を書き換える案は採らない。対象プロジェクトのworktree内で
# Agent Runnerが`python`/`pytest`/`ruff`等（対象プロジェクト自身のCLAUDE.mdの
# 開発ワークフローで使うもの）を呼んだ場合に、オーケストレータ自身のvenvに同名で
# 同梱されている`python`/`pytest`/`ruff`（`orchestrator/pyproject.toml`のdev依存）
# を誤ってPATH解決してしまい、対象プロジェクトのツールチェーンをサイレントに
# シャドーイングする恐れがあるため。
def _resolve_ollama_bench_path() -> str:
    # `.resolve()`は使わない。venvのpythonバイナリはHomebrew等が管理する実体への
    # symlinkであることが多く、解決すると`ollama-bench`が存在しない実体側のbin
    # ディレクトリ（例: Homebrew CellarのFrameworks/.../bin）を指してしまう。
    # `sys.executable`はvenv経由で起動された場合そのvenvのbinパスをそのまま
    # 報告するため、symlinkのまま親ディレクトリを使う。
    candidate = Path(sys.executable).parent / "ollama-bench"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("ollama-bench")
    if found:
        return found
    logger.warning(
        "ollama-bench の絶対パスを解決できませんでした（sys.executable隣接・PATH"
        "いずれにも見つからず）。OLLAMA_BENCH_PATHにはバレのコマンド名を設定する"
        "ため、Agent Runnerのworktree側でPATH解決できず利用量が記録されない"
        "可能性があります。"
    )
    return "ollama-bench"


def _init_log_file(repo: str, issue_number: int, *, logs_dir: Path, timestamp: str) -> Path:
    """ログファイルを実行開始時点で作成する（issue #49）。

    以降は`_stream_process_output`がプロセスの標準出力を1行読むたびに都度
    このファイルへappendする。実行完了を待たずログが逐次伸びていくことで、
    `tail -f`での実行中の進捗確認を可能にする。
    """
    log_dir = logs_dir / repo
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{timestamp}.log"
    log_path.write_text(f"issue: #{issue_number}\n", encoding="utf-8")
    return log_path


def cleanup_old_agent_logs(repo_log_dir: Path, retention_days: int, now: NowFn) -> None:
    """保持日数を超えて更新されていないAgent Runner個別実行ログを削除する。

    mtime基準で判定する。`_stream_process_output`は1行書くたびに`flush()`する
    ため、実行中のファイルは常にmtimeが「今」に近い状態を保つ。ファイル名に
    埋め込まれた実行開始時刻ではなくmtimeで判定することで、実行中のファイルは
    経過日数のカウントが始まらず、追加のフラグ管理（`DispatchQueue.is_active()`
    の参照等）なしに「実行中は保護・完了後は経過日数で削除」を実現できる
    （issue #114）。書き込み中のファイルを日付境界で分割する仕組みではないため、
    「1実行＝1ファイル」の書き込み方式自体は変更しない。
    """
    if not repo_log_dir.is_dir():
        return

    cutoff = now().timestamp() - retention_days * 86400
    for log_path in repo_log_dir.glob("*.log"):
        if log_path.stat().st_mtime < cutoff:
            log_path.unlink()


def _write_error_log(
    repo: str, issue_number: int, error_message: str, *, logs_dir: Path, timestamp: str
) -> Path:
    log_path = _init_log_file(repo, issue_number, logs_dir=logs_dir, timestamp=timestamp)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(error_message + "\n")
    return log_path


def _stream_process_output(process: subprocess.Popen, log_path: Path) -> str:
    """プロセスの標準出力を1行読むたびにログファイルへflushしながら全文を返す。

    `run_agent_runner`は`stderr=subprocess.STDOUT`でプロセスを起動するため、
    標準エラー出力もこのストリームに混在する（別スレッドでの並行読み取りは
    実装を複雑にする割に、取りこぼし防止という目的に対しては`STDOUT`への
    合流で十分なため採用しなかった）。
    """
    lines: list[str] = []
    assert process.stdout is not None
    with log_path.open("a", encoding="utf-8") as log_file:
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            lines.append(line)
    return "".join(lines)


def _parse_result_payload(stdout: str) -> dict | None:
    """NDJSON（`stream-json`）出力から、最後の`"type":"result"`イベントを取り出す。

    stderrが同一ストリームに合流しJSONとして解釈できない行が混ざり得るため、
    各行を個別にパースし解釈できない行はスキップする。
    """
    payload: dict | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("type") == "result":
            payload = data
    return payload


def _extract_summary(payload: dict | None) -> str | None:
    result = payload.get("result") if payload else None
    return result if isinstance(result, str) else None


@dataclass
class _RunErrorInfo:
    is_error: bool
    api_error_status: int | None
    result_text: str | None
    limit_reset_text: str | None


# issue #146: 429到達時の異常終了通知（`_build_failure_comment`）でも、ここと
# 同じ`is_error`/`api_error_status`/`limit_reset_text`の抽出が必要になった。
# 2箇所で独立に同じ抽出ロジックを書くと、将来どちらか一方だけを変更した際に
# issueコメントとusage.dbの記録内容が食い違いかねないため、抽出処理自体を
# 共通化する。
def _classify_run_error(payload: dict | None) -> _RunErrorInfo:
    if payload is None:
        return _RunErrorInfo(
            is_error=False, api_error_status=None, result_text=None, limit_reset_text=None
        )

    is_error = bool(payload.get("is_error"))
    api_error_status = payload.get("api_error_status")
    result_text = payload.get("result")
    result_text = result_text if isinstance(result_text, str) else None

    limit_reset_text = None
    if is_error and api_error_status == 429 and result_text:
        limit_reset_text = parse_limit_reset_text(result_text) or result_text

    return _RunErrorInfo(
        is_error=is_error,
        api_error_status=api_error_status,
        result_text=result_text,
        limit_reset_text=limit_reset_text,
    )


# issue #60: `_extract_summary`は`result`フィールドしか使わず、`total_cost_usd`/
# `usage.*`/`modelUsage.*`を破棄していたため、利用量モニターに実データを
# 表示できなかった。ここでモデル別の利用量レコードに変換し、usage_store経由で
# 永続化する（正確な利用率%はこの経路では取得できないため、日単位の使用量記録に
# 転換する方針。docs/basic-design.md 2-2参照）。
def _extract_usage_records(
    payload: dict | None, *, repo: str, issue_number: int
) -> list[UsageRecord]:
    if payload is None:
        return []

    error_info = _classify_run_error(payload)
    is_error = error_info.is_error
    error_message = error_info.result_text if is_error else None

    common_error_fields = {
        "is_error": is_error,
        "api_error_status": error_info.api_error_status,
        "error_message": error_message,
        "limit_reset_text": error_info.limit_reset_text,
    }

    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        return [
            UsageRecord(
                repo=repo,
                issue_number=issue_number,
                model=model_name,
                input_tokens=int(stats.get("inputTokens", 0) or 0),
                output_tokens=int(stats.get("outputTokens", 0) or 0),
                cache_creation_input_tokens=int(stats.get("cacheCreationInputTokens", 0) or 0),
                cache_read_input_tokens=int(stats.get("cacheReadInputTokens", 0) or 0),
                total_cost_usd=stats.get("costUSD"),
                **common_error_fields,
            )
            for model_name, stats in model_usage.items()
            if isinstance(stats, dict)
        ]

    usage = payload.get("usage")
    if isinstance(usage, dict):
        model = payload.get("model")
        return [
            UsageRecord(
                repo=repo,
                issue_number=issue_number,
                model=model if isinstance(model, str) else "unknown",
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                total_cost_usd=payload.get("total_cost_usd"),
                **common_error_fields,
            )
        ]

    if is_error:
        # リミット到達等でusage自体が空でも、リミット到達の事実は記録する。
        return [
            UsageRecord(
                repo=repo,
                issue_number=issue_number,
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                **common_error_fields,
            )
        ]

    return []


# issue #144: AGENT_RUNNER_PR_ISSUE_REFERENCE_INSTRUCTIONで「PR本文にCloses #<issue番号>を
# 含めること」を指示しているが、これはAIの自己申告に委ねる運用であり、指示が守られず
# PR本文にissue番号への言及が一切無い場合（issue #82が対策したcross-referenceイベント
# 未生成のケースとは異なり、そもそも言及自体が存在しないため`resolve_pr_number`の
# フォールバック（OPEN PR全文検索）でも解決できない）を検知・補完する仕組みが無かった
# （issue #136 / PR #143で実際に発生）。issue #78の「ラベル遷移漏れをオーケストレータ側で
# 決定的に補完する」パターンを踏襲し、status:in-review到達時にPRのissue参照を検証する。
#
# この処理自体の失敗（`gh`/`git`呼び出しの一時的な失敗等）は、呼び出し元の
# `run_agent_runner`が`DispatchQueue._run_worker`（例外を捕捉せず、失敗すると
# ワーカースレッドが`self._running`から自身を除去できないまま停止し、以後その
# プロジェクトの全ディスパッチがキューに溜まったまま処理されなくなる）から
# 呼ばれるため、ここで捕捉せずに伝播させるとオーケストレータ全体を壊しかねない。
# PR参照の補完はあくまで「できれば直す」ベストエフォートの後始末であり、この
# 処理の成否がissueの状態遷移（既に`status:in-review`に到達済み）自体を左右する
# 必要は無いため、失敗時は警告ログに留めて握りつぶす。
def _ensure_pr_issue_reference(
    repo: str,
    issue_number: int,
    worktree_path: Path,
    *,
    resolve_pr_number_fn: ResolvePrNumberFn,
    get_current_branch_fn: GetCurrentBranchFn,
    find_open_pr_by_branch_fn: FindOpenPrByBranchFn,
    append_pr_issue_reference_fn: AppendPrIssueReferenceFn,
) -> None:
    """status:in-review到達時、issueに紐づくPRを解決できるか確認し、できなければ補完する。

    `resolve_pr_number_fn`（cross-referenceイベント・OPEN PR全文検索）のどちらでも
    解決できない場合、Agent Runnerセッション終了時点のworktreeのカレントブランチを
    headとするOPEN PRを検索し、見つかればPR本文へ`Closes #<issue番号>`を追記する。
    ブランチからも一意にPRを特定できない場合や`gh`/`git`呼び出し自体が失敗した場合は
    警告ログに留め、ラベル遷移等の強制操作は行わない（PR自体は既に作成されており
    issueの状態遷移自体は正しいため）。
    """
    try:
        if resolve_pr_number_fn(repo, issue_number) is not None:
            return

        branch = get_current_branch_fn(str(worktree_path))
        pr = find_open_pr_by_branch_fn(repo, branch)
        if pr is None:
            logger.warning(
                "issue %s#%d はstatus:in-reviewだがPRへのissue参照を解決できず、"
                "worktreeのカレントブランチ(%s)からも一意なOPEN PRを特定できませんでした。",
                repo,
                issue_number,
                branch,
            )
            return

        existing_body = pr.get("body") or ""
        if f"Closes #{issue_number}" in existing_body:
            # 前回の呼び出しで既に追記済みだが、GitHub側のcross-reference
            # イベント生成がまだ反映されておらず`resolve_pr_number_fn`が
            # 追いついていないだけのケース。二重追記を避けるため何もしない。
            return

        append_pr_issue_reference_fn(repo, pr["number"], issue_number, existing_body)
    except subprocess.CalledProcessError:
        logger.warning(
            "issue %s#%d のPR参照補完処理中にghまたはgitコマンドが失敗しました。",
            repo,
            issue_number,
            exc_info=True,
        )


# issue #146: プロセスが異常終了（returncode != 0）した際、原因を問わず一律で
# 「ログを見てください」という文面を投稿していた。この手の異常終了は大抵の場合
# APIリミット到達（429）が原因であり、`_extract_usage_records`（issue #60）が
# 既に検知している`is_error`/`api_error_status`をここでも参照し、429の場合は
# ログパスの代わりにリミット到達である旨と解除予定時刻を伝える。429以外の
# 異常終了（予期しない例外等）ではデバッグに必要なため従来通りログパスを含める。
def _build_failure_comment(payload: dict | None, *, returncode: int, log_path: Path) -> str:
    error_info = _classify_run_error(payload)

    # `result`が空/非文字列で解除予定時刻等の情報が一切得られない場合、
    # ログパスを省いた文面では人間が調査する手がかりが無くなってしまうため、
    # 429以外の異常終了と同じ従来通りのログパス付きメッセージにフォールバックする。
    if error_info.is_error and error_info.api_error_status == 429 and error_info.limit_reset_text:
        return (
            ":warning: Claude CodeのAPI利用リミットに達したため停止しました。"
            f"（{error_info.limit_reset_text}）"
        )

    return f":warning: Agent Runnerが異常終了しました（終了コード: {returncode}）。ログ: {log_path}"


def run_agent_runner(
    project: Project,
    issue_number: int,
    message: str,
    *,
    popen: PopenFn = subprocess.Popen,
    post_comment: PostCommentFn = gh_post_comment,
    get_labels: GetLabelsFn = gh_get_labels,
    add_label: AddLabelFn = gh_add_label,
    remove_label: RemoveLabelFn = gh_remove_label,
    logs_dir: Path = DEFAULT_LOGS_DIR,
    get_session_id_fn: GetSessionIdFn = get_session_id,
    persist_session_id_fn: PersistSessionIdFn = persist_session_id,
    record_usage_fn: RecordUsageFn = store_record_usage,
    now: NowFn = lambda: datetime.now(UTC),
    new_uuid: UuidFn = lambda: str(uuid.uuid4()),
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
    resolve_pr_number_fn: ResolvePrNumberFn = gh_resolve_pr_number,
    get_current_branch_fn: GetCurrentBranchFn = gh_get_current_branch,
    find_open_pr_by_branch_fn: FindOpenPrByBranchFn = gh_find_open_pr_by_branch,
    append_pr_issue_reference_fn: AppendPrIssueReferenceFn = gh_append_pr_issue_reference,
) -> AgentRunResult:
    """Claude Code CLIをワンショット実行し、結果をissueコメント・ログに反映する。

    セッションはissue単位（`get_session_id_fn`/`persist_session_id_fn`が
    `(repo, issue_number)`をキーに管理、[[docs/basic-design.md 3-1]]参照）で
    保持する。プロジェクト単位で1つのセッションを共有すると、あるissueが
    判断待ちで止まっている間に別issueが同じセッションで進行し、後から前者を
    resumeした際に後者issueの文脈を引きずってしまう（issue #32）。
    """
    # ログファイル名はJST基準（issue #114）。`now`自体は既定でUTCを返す
    # （record_usage_fn側のrecorded_at契約を維持するため、`now()`の戻り値
    # そのものは変更せずJSTへ変換するだけに留める）。
    timestamp = now().astimezone(JST).strftime("%Y%m%dT%H%M%S")
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
        log_path = _write_error_log(
            project.repo, issue_number, error_message, logs_dir=logs_dir, timestamp=timestamp
        )
        cleanup_old_agent_logs(logs_dir / project.repo, log_retention_days, now)
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

    log_path = _init_log_file(project.repo, issue_number, logs_dir=logs_dir, timestamp=timestamp)
    # issue #107: AGENT_RUNNER_LOCAL_LLM_INSTRUCTIONが参照する`$OLLAMA_BENCH_PATH`を
    # 子プロセス（`claude -p`、およびそのBashツールが起動するシェル）の環境変数として
    # 渡す。PATH自体は書き換えず、この1変数だけを追加する。
    env = {**os.environ, "OLLAMA_BENCH_PATH": _resolve_ollama_bench_path()}
    process = popen(
        command,
        cwd=str(worktree_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    stdout_text = _stream_process_output(process, log_path)
    returncode = process.wait()

    if not resume:
        persist_session_id_fn(project.repo, issue_number, session_id)

    success = returncode == 0
    payload = _parse_result_payload(stdout_text)
    usage_records = _extract_usage_records(payload, repo=project.repo, issue_number=issue_number)
    if usage_records:
        record_usage_fn(usage_records, now=now)

    if success:
        summary = (
            _extract_summary(payload)
            or "(実行結果の要約を取得できませんでした。ログを参照してください。)"
        )
        post_comment(project.repo, issue_number, f"Agent Runner実行結果:\n{summary}")

        # issue #78: プロセスは正常終了（exit 0）したが、Agent Runnerが
        # AGENT_RUNNER_LABEL_INSTRUCTIONの自己申告ラベル遷移を怠るケースが
        # あり、その場合`success = True`のこの分岐しか通らないため放置される
        # と判断待ちが宙に浮く（issue #70で発生）。正常終了時、issueは必ず
        # 「PR作成済み（status:in-review）」「人間への確認が必要
        # （needs-human-decision）」のいずれかに到達している設計のため、
        # status:in-progressのまま変化がなければ常に異常とみなし、
        # needs-human-decisionへ強制的にフォールバックさせる。
        current_labels = get_labels(project.repo, issue_number)
        if STATUS_IN_PROGRESS in current_labels:
            transition_label(
                project.repo,
                issue_number,
                STATUS_NEEDS_HUMAN_DECISION,
                get_labels=get_labels,
                add_label=add_label,
                remove_label=remove_label,
            )
        elif STATUS_IN_REVIEW in current_labels:
            _ensure_pr_issue_reference(
                project.repo,
                issue_number,
                worktree_path,
                resolve_pr_number_fn=resolve_pr_number_fn,
                get_current_branch_fn=get_current_branch_fn,
                find_open_pr_by_branch_fn=find_open_pr_by_branch_fn,
                append_pr_issue_reference_fn=append_pr_issue_reference_fn,
            )
    else:
        error_comment = _build_failure_comment(payload, returncode=returncode, log_path=log_path)
        post_comment(project.repo, issue_number, error_comment)
        transition_label(
            project.repo,
            issue_number,
            STATUS_NEEDS_HUMAN_DECISION,
            get_labels=get_labels,
            add_label=add_label,
            remove_label=remove_label,
        )

    cleanup_old_agent_logs(logs_dir / project.repo, log_retention_days, now)
    return AgentRunResult(
        repo=project.repo,
        issue_number=issue_number,
        exit_code=returncode,
        log_path=log_path,
        session_id=session_id,
        success=success,
    )
