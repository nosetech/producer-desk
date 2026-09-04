"""自走タスク本体の実行手段（(A) Claude Code CLI直利用／(B) LiteLLM Proxy経由）の解決。

仕様: docs/basic-design.md 4章「実行手段の選択」「issueコメントでの都度指示」
issue #148・#174・#176

実行手段は以下の優先順位で解決する。
1. 今回のディスパッチメッセージ（issueコメント本文）に含まれる都度上書き指令
   （後述の`/model`ディレクティブ）。検出した場合は同時に
   `execution_override_store`へ永続化し、以降のディスパッチ（次回`--resume`時等）
   でもこの指定が使われるようにする。
2. issueに保存済みの都度上書き指定（`execution_override_store`）。
3. プロジェクトのデフォルト設定（`config/projects.yaml`、`Project.execution_mode`）。

**都度上書きディレクティブの構文（issue #176で確定）**: 独立した行として
`/model claude_code` または `/model litellm:<LiteLLM Proxyのモデルエイリアス>` を
書く（前後の空白は許容、行頭の`/model`のみを見るため本文中の他の説明文とは
干渉しない）。ディレクティブ行はAgent Runnerへ渡すプロンプト本文からは取り除く
（`strip_override_directive`）。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from orchestrator.config import (
    EXECUTION_MODE_CLAUDE_CODE,
    EXECUTION_MODE_LITELLM_PROXY,
    Project,
)
from orchestrator.execution_override_store import get_execution_override
from orchestrator.execution_override_store import (
    persist_execution_override as store_persist_execution_override,
)

# 行頭（前後の空白は許容）の `/model claude_code` または `/model litellm:<alias>` を
# 都度上書きディレクティブとして認識する。`re.MULTILINE`でメッセージ中のどの行に
# あっても検出する。エイリアス部分はLiteLLM Proxy側のmodel_nameがコロン・スラッシュ
# を含みうる（例: `ollama/qwen2.5-coder:7b`）ため、行末までを非空白として扱う。
_OVERRIDE_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*/model[ \t]+(claude_code|litellm:(?P<alias>\S+))[ \t]*$",
    re.MULTILINE,
)

GetExecutionOverrideFn = Callable[..., dict | None]
PersistExecutionOverrideFn = Callable[..., None]

# 指示コメントが`/model ...`ディレクティブのみで構成されていた場合、ディレクティブ
# 行を取り除くとプロンプトが空文字列になってしまう（`claude -p ""`は意図しない
# 空プロンプト送信になる）。そのようなケースでは実行手段の切り替えのみが目的で
# あり作業指示そのものは無い（=作業を継続してほしい）と解釈し、代わりにこの文言を
# プロンプトとして使う。
_DIRECTIVE_ONLY_FALLBACK_MESSAGE = "（実行手段の変更のみの指示です。作業を継続してください。）"


@dataclass
class ExecutionSettings:
    execution_mode: str
    litellm_model: str | None


def parse_override_directive(message: str) -> ExecutionSettings | None:
    """メッセージ本文から`/model`都度上書きディレクティブを抽出する。

    複数回書かれていた場合は最後に出現したものを採用する（`/model`を書き間違えて
    訂正した場合、後の行が意図した指定であるはずのため）。
    """
    match = None
    for match in _OVERRIDE_DIRECTIVE_PATTERN.finditer(message):
        pass
    if match is None:
        return None

    alias = match.group("alias")
    if alias:
        return ExecutionSettings(execution_mode=EXECUTION_MODE_LITELLM_PROXY, litellm_model=alias)
    return ExecutionSettings(execution_mode=EXECUTION_MODE_CLAUDE_CODE, litellm_model=None)


def strip_override_directive(message: str) -> str:
    """プロンプト本文として送る前に`/model`ディレクティブ行を取り除く。

    ディレクティブは実行手段の切り替え専用の指示でありAgent Runner自身への作業
    指示ではないため、そのままプロンプトに残すと無関係な行として混入する。
    """
    stripped = _OVERRIDE_DIRECTIVE_PATTERN.sub("", message)
    # 空行の連続が残ることがあるため、前後の余白のみ軽く整える
    # （途中の空行はメッセージの意図的な段落区切りの可能性があるため保持する）。
    return stripped.strip()


def resolve_execution_settings(
    project: Project,
    repo: str,
    issue_number: int,
    message: str,
    *,
    get_execution_override_fn: GetExecutionOverrideFn = get_execution_override,
    persist_execution_override_fn: PersistExecutionOverrideFn = store_persist_execution_override,
) -> tuple[ExecutionSettings, str]:
    """今回のディスパッチで使う実行手段と、ディレクティブを取り除いたメッセージを返す。"""
    override = parse_override_directive(message)
    if override is not None:
        persist_execution_override_fn(
            repo, issue_number, override.execution_mode, override.litellm_model
        )
        stripped = strip_override_directive(message)
        return override, (stripped or _DIRECTIVE_ONLY_FALLBACK_MESSAGE)

    stored = get_execution_override_fn(repo, issue_number)
    if stored is not None:
        return (
            ExecutionSettings(
                execution_mode=stored["execution_mode"],
                litellm_model=stored.get("litellm_model"),
            ),
            message,
        )

    # `project.execution_mode`/`project.litellm_model`は`server.py`の
    # `PATCH /api/projects/{repo}/settings`から別スレッドで書き換えられうるため、
    # 個別に読まず`snapshot_execution_settings`で一貫した組として取得する
    # （`Project.execution_lock`参照）。
    default_mode, default_model = project.snapshot_execution_settings()
    return (
        ExecutionSettings(execution_mode=default_mode, litellm_model=default_model),
        message,
    )
