"""Agent Runnerプロンプト設定の読み込み・書き込み（issue #149）。

Agent Runner起動時に`--append-system-prompt`で渡す指示文は、コード内蔵のデフォルト値を
フォールバックとしつつ、`config/prompts.yaml`（キー→本文の上書き分のみを保持）で
差し替えられる。`config/projects.yaml`と同様、オーケストレータのみが読む設定ファイルで
あり、「GitHub Issues/Projectsが正のデータストア」という方針（CLAUDE.md）はissueの
状態管理に関するものなので、独自DBは新設しない。

`config/prompts.yaml`は`prompts`キーのみを持つ（保存時は`prompts`キー以外を書き戻さない）。
書き込みは同一ディレクトリの一時ファイルへ書いてから`os.replace`で差し替えるため、
Agent Runner起動や一覧取得が書き込み途中の内容を読むことはない。YAMLが壊れている
場合、読み出し側はデフォルトにフォールバックし、書き込み側は壊れたファイルを
`prompts.yaml.broken-<時刻>`へ退避したうえで上書きする（UIから復旧できなくなるのを防ぐ）。

誤編集でシステムが壊れるリスクを抑えるため、以下の検証を保存時に行う。
- プレースホルダは各項目の`placeholders`（`{repo}`・`{issue_number}`・`{user_name}`のうち
  展開されるもの）のみ許可する（それ以外の`{xxx}`は拒否）
- 各プロンプトに定義された必須トークン（状態ラベル名・機械可読マーカー等、オーケス
  トレータが依存する文字列）が含まれていなければ拒否する。検証は文字列の**部分一致のみ**
  で、トークンの前後の書式（マーカーの閉じ`-->`等）が正しいかまでは確認しない

プレースホルダは`str.format`ではなく単純な文字列置換で展開する。JSON例示の波括弧を
`{{ }}`でエスケープさせる必要がなく、編集者がプレースホルダ構文を意識せずに済む。

仕様: docs/basic-design.md 3-6（Agent Runnerプロンプト設定管理）
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from orchestrator.config import REPO_ROOT

logger = logging.getLogger(__name__)

PROMPTS_PATH_ENV = "ORCHESTRATOR_PROMPTS_PATH"
DEFAULT_PROMPTS_PATH = REPO_ROOT / "config" / "prompts.yaml"

# 指示文本文中で使えるプレースホルダ。起動時に置換される。`user_name`はユーザーの呼称
# （下記`USER_NAME_SPEC`）。
ALLOWED_PLACEHOLDERS: tuple[str, ...] = ("repo", "issue_number", "user_name")

_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# config/prompts.yamlの読み書き（read-modify-write）はThreadingHTTPServer配下の別
# スレッドから同時に呼ばれうるため、プロセス内でこのロックにより直列化する
# （config.pyの`_PROJECTS_YAML_WRITE_LOCK`と同じ方針）。
_PROMPTS_YAML_WRITE_LOCK = threading.Lock()


DEFAULT_USER_NAME = "ユーザー"


@dataclass(frozen=True)
class RequiredToken:
    """プロンプト本文に必ず含めなければならない文字列と、その理由。"""

    token: str
    reason: str


@dataclass(frozen=True)
class PromptSpec:
    key: str
    title: str
    description: str
    default: str
    required_tokens: tuple[RequiredToken, ...] = ()
    # この項目の本文で使えるプレースホルダ。展開されない項目（定型コメント・呼称自身）は空にする。
    placeholders: tuple[str, ...] = ALLOWED_PLACEHOLDERS
    # Falseの項目は改行・波括弧を含められない（呼称のような短い語句）。
    multiline: bool = True


class PromptStorageError(Exception):
    """`config/prompts.yaml`への書き込み失敗（ディスクフル・権限等）。"""


class PromptValidationError(ValueError):
    """プロンプトの保存時検証エラー。`errors`にユーザー向けメッセージを列挙する。"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_prompt_text(spec: PromptSpec, text: str) -> list[str]:
    """本文を検証し、エラーメッセージのリストを返す（空なら有効）。"""
    errors: list[str] = []
    if not text.strip():
        errors.append("本文が空です")
    if not spec.multiline and ("\n" in text or "{" in text or "}" in text):
        errors.append("改行・波括弧（{ }）は使用できません")
    for name in dict.fromkeys(_PLACEHOLDER_PATTERN.findall(text)):
        if name not in spec.placeholders:
            usable = ", ".join("{" + p + "}" for p in spec.placeholders) or "なし"
            errors.append(f"未知のプレースホルダ {{{name}}} が含まれています（使用可能: {usable}）")
    for required in spec.required_tokens:
        if required.token not in text:
            errors.append(f"必須トークン {required.token} が含まれていません")
    return errors


def render_prompt(text: str, *, repo: str, issue_number: int, user_name: str) -> str:
    """プレースホルダを展開する。

    `text`と`user_name`は`validate_prompt_text`を通過した値であることを前提とする
    （`resolve_prompt_text`経由）。`user_name`は波括弧を含められず、`repo`は
    `owner/name`形式のため、置換順に依存した二重展開は起きない。この前提を崩す変更
    （検証を通さない値の展開等）をする場合は展開方式を見直すこと。
    """
    return (
        text.replace("{repo}", repo)
        .replace("{issue_number}", str(issue_number))
        .replace("{user_name}", user_name)
    )


def _resolve_path(path: Path | None) -> Path:
    if path is not None:
        return path
    return Path(os.environ.get(PROMPTS_PATH_ENV, str(DEFAULT_PROMPTS_PATH)))


def load_overrides(path: Path | None = None) -> dict[str, str]:
    """`config/prompts.yaml`の上書き分を読み込む。ファイルが無ければ空。"""
    resolved = _resolve_path(path)
    if not resolved.exists():
        return {}
    with resolved.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    prompts = data.get("prompts", {}) if isinstance(data, dict) else {}
    if not isinstance(prompts, dict):
        return {}
    return {str(k): v for k, v in prompts.items() if isinstance(v, str)}


def load_overrides_safe(path: Path | None = None) -> dict[str, str]:
    """`load_overrides`のフォールバック版。読み込み失敗時は警告ログを出して空を返す。"""
    try:
        return load_overrides(path)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("config/prompts.yamlを読み込めないためデフォルトを使用します: %s", e)
        return {}


def _write_overrides(overrides: dict[str, str], path: Path) -> None:
    """一時ファイルへ書いてから`os.replace`で差し替える（読み手に途中状態を見せない）。"""
    content = yaml.safe_dump({"prompts": overrides}, allow_unicode=True, sort_keys=False)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except OSError as e:
        raise PromptStorageError(f"config/prompts.yamlを書き込めませんでした: {e}") from e


def _load_overrides_for_update(path: Path) -> dict[str, str]:
    """更新用の読み込み。YAMLが壊れていれば退避して空から始める（ロック保持中に呼ぶ）。"""
    try:
        return load_overrides(path)
    except yaml.YAMLError as e:
        backup = path.with_name(f"{path.name}.broken-{datetime.now():%Y%m%d%H%M%S}")
        try:
            os.replace(path, backup)
        except OSError as oe:
            raise PromptStorageError(
                f"壊れたconfig/prompts.yamlを退避できませんでした: {oe}"
            ) from oe
        logger.warning("config/prompts.yamlが壊れていたため %s へ退避しました: %s", backup, e)
        return {}
    except OSError as e:
        raise PromptStorageError(f"config/prompts.yamlを読み込めませんでした: {e}") from e


def resolve_prompt_text(spec: PromptSpec, overrides: dict[str, str]) -> str:
    """上書きがあればそれを、無い・不正な場合はデフォルトを返す。

    config/prompts.yamlが手編集された等で検証に通らない上書きが入っていても、
    Agent Runnerの起動自体を止めないようデフォルトにフォールバックする。
    """
    override = overrides.get(spec.key)
    if override is None:
        return spec.default
    errors = validate_prompt_text(spec, override)
    if errors:
        logger.warning(
            "プロンプト %s の上書き設定が不正なためデフォルトを使用します: %s",
            spec.key,
            "; ".join(errors),
        )
        return spec.default
    return override


def load_prompt_text(spec: PromptSpec, path: Path | None = None) -> str:
    """`spec`の現在の本文（上書き or デフォルト）を返す。YAML読み込み失敗時はデフォルト。"""
    return resolve_prompt_text(spec, load_overrides_safe(path))


def save_prompt_override(spec: PromptSpec, text: str, path: Path | None = None) -> None:
    """検証のうえ`spec`の上書きを保存する。デフォルトと同一なら上書きを削除する。"""
    errors = validate_prompt_text(spec, text)
    if errors:
        raise PromptValidationError(errors)
    resolved = _resolve_path(path)
    with _PROMPTS_YAML_WRITE_LOCK:
        overrides = _load_overrides_for_update(resolved)
        if text == spec.default:
            overrides.pop(spec.key, None)
        else:
            overrides[spec.key] = text
        _write_overrides(overrides, resolved)


def reset_prompt_override(spec: PromptSpec, path: Path | None = None) -> None:
    """`spec`の上書きを削除し、デフォルトに戻す。"""
    resolved = _resolve_path(path)
    with _PROMPTS_YAML_WRITE_LOCK:
        overrides = _load_overrides_for_update(resolved)
        if overrides.pop(spec.key, None) is not None:
            _write_overrides(overrides, resolved)


def describe_prompt(spec: PromptSpec, overrides: dict[str, str]) -> dict:
    """API応答用の1プロンプト分の情報。`overrides`は`load_overrides_safe`の結果。"""
    text = resolve_prompt_text(spec, overrides)
    # 説明文・必須トークンの理由に含まれる{user_name}は、設定済みの呼称で展開して返す。
    user_name = resolve_prompt_text(USER_NAME_SPEC, overrides)

    def with_user_name(s: str) -> str:
        return s.replace("{user_name}", user_name)

    return {
        "key": spec.key,
        "title": spec.title,
        "description": with_user_name(spec.description),
        "text": text,
        "default": spec.default,
        "is_default": text == spec.default,
        "required_tokens": [
            {"token": r.token, "reason": with_user_name(r.reason)} for r in spec.required_tokens
        ],
        "placeholders": list(spec.placeholders),
        "multiline": spec.multiline,
    }


def describe_prompts(specs: tuple[PromptSpec, ...], path: Path | None = None) -> list[dict]:
    """複数プロンプトの情報。`config/prompts.yaml`は1回だけ読む。"""
    overrides = load_overrides_safe(path)
    return [describe_prompt(spec, overrides) for spec in specs]


# issue #149: 指示文・最終応答でユーザー自身を指す語の呼称。
# プロンプト設定の1項目として編集でき、各指示文の`{user_name}`に展開される。
USER_NAME_SPEC = PromptSpec(
    key="user_name",
    title="ユーザーの呼称",
    description="指示文・最終応答でユーザー自身を指すときの呼び名。各指示文中の呼称として使われます",
    default=DEFAULT_USER_NAME,
    placeholders=(),
    multiline=False,
)
