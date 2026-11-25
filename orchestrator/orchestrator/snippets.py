"""返信欄に挿入する定型文の読み込み・書き込み（issue #323）。

ダッシュボードの返信欄（ComposerBarの返信モード）で選んでカーソル位置に挿入する
定型文を、`config/snippets.yaml`に保存する。全プロジェクト共通の固定文で、
プレースホルダは扱わない。`config/prompts.yaml`（prompts.py）と同様、アプリケーション
設定のファイルであり、issueの状態管理（GitHubを正とする方針）には関与しない。

ファイルは`snippets`キーのみを持ち、値は`{id, title, body}`の配列（配列順が表示順）。
書き込みは同一ディレクトリの一時ファイルへ書いてから`os.replace`で差し替える。
YAMLが壊れている場合、一覧取得は空配列を返し、書き込み側は壊れたファイルを
`snippets.yaml.broken-<時刻>`へ退避したうえで空から書き直す（UIから復旧できるように）。

仕様: docs/basic-design.md 2-5（返信欄の定型文管理）
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from orchestrator.config import REPO_ROOT

logger = logging.getLogger(__name__)

SNIPPETS_PATH_ENV = "ORCHESTRATOR_SNIPPETS_PATH"
DEFAULT_SNIPPETS_PATH = REPO_ROOT / "config" / "snippets.yaml"

MAX_TITLE_LENGTH = 50
MAX_BODY_LENGTH = 2000
MAX_SNIPPETS = 50

# read-modify-writeはThreadingHTTPServer配下の別スレッドから同時に呼ばれうるため直列化する。
_SNIPPETS_YAML_WRITE_LOCK = threading.Lock()


class SnippetStorageError(Exception):
    """`config/snippets.yaml`の読み書き失敗（ディスクフル・権限等）。"""


class SnippetNotFoundError(LookupError):
    """指定したidの定型文が存在しない。"""


class SnippetValidationError(ValueError):
    """保存時の検証エラー。`errors`にユーザー向けメッセージを列挙する。"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _resolve_path(path: Path | None) -> Path:
    if path is not None:
        return path
    return Path(os.environ.get(SNIPPETS_PATH_ENV, str(DEFAULT_SNIPPETS_PATH)))


def validate_snippet(title: object, body: object) -> list[str]:
    """タイトル・本文を検証し、エラーメッセージのリストを返す（空なら有効）。"""
    errors: list[str] = []
    if not isinstance(title, str):
        errors.append("タイトルは文字列である必要があります")
    elif not title.strip():
        errors.append("タイトルが空です")
    elif "\n" in title or "\r" in title:
        errors.append("タイトルに改行は使用できません")
    elif len(title) > MAX_TITLE_LENGTH:
        errors.append(f"タイトルは{MAX_TITLE_LENGTH}文字以内にしてください")
    if not isinstance(body, str):
        errors.append("本文は文字列である必要があります")
    elif not body.strip():
        errors.append("本文が空です")
    elif len(body) > MAX_BODY_LENGTH:
        errors.append(f"本文は{MAX_BODY_LENGTH}文字以内にしてください")
    return errors


def _parse(data: object) -> list[dict]:
    """YAMLの内容から有効な定型文だけを取り出す（不正な要素は読み飛ばす）。"""
    items = data.get("snippets", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        sid, title, body = item.get("id"), item.get("title"), item.get("body")
        if not (isinstance(sid, str) and sid and sid not in seen):
            continue
        if not (isinstance(title, str) and isinstance(body, str)):
            continue
        seen.add(sid)
        result.append({"id": sid, "title": title, "body": body})
    return result


def load_snippets(path: Path | None = None) -> list[dict]:
    """定型文一覧を読み込む。ファイルが無ければ空。読み込み失敗時は例外を送出する。"""
    resolved = _resolve_path(path)
    if not resolved.exists():
        return []
    with resolved.open(encoding="utf-8") as f:
        return _parse(yaml.safe_load(f))


def load_snippets_safe(path: Path | None = None) -> list[dict]:
    """`load_snippets`のフォールバック版。読み込み失敗時は警告ログを出して空を返す。"""
    try:
        return load_snippets(path)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("config/snippets.yamlを読み込めないため空として扱います: %s", e)
        return []


def _write(snippets: list[dict], path: Path) -> None:
    content = yaml.safe_dump({"snippets": snippets}, allow_unicode=True, sort_keys=False)
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
        raise SnippetStorageError(f"config/snippets.yamlを書き込めませんでした: {e}") from e


def _load_for_update(path: Path) -> list[dict]:
    """更新用の読み込み。YAMLが壊れていれば退避して空から始める（ロック保持中に呼ぶ）。"""
    try:
        return load_snippets(path)
    except yaml.YAMLError as e:
        backup = path.with_name(f"{path.name}.broken-{datetime.now():%Y%m%d%H%M%S}")
        try:
            os.replace(path, backup)
        except OSError as oe:
            raise SnippetStorageError(
                f"壊れたconfig/snippets.yamlを退避できませんでした: {oe}"
            ) from oe
        logger.warning("config/snippets.yamlが壊れていたため %s へ退避しました: %s", backup, e)
        return []
    except OSError as e:
        raise SnippetStorageError(f"config/snippets.yamlを読み込めませんでした: {e}") from e


def _validated(title: object, body: object) -> tuple[str, str]:
    errors = validate_snippet(title, body)
    if errors:
        raise SnippetValidationError(errors)
    assert isinstance(title, str) and isinstance(body, str)
    return title.strip(), body


def create_snippet(title: object, body: object, path: Path | None = None) -> dict:
    """定型文を末尾に追加し、追加した定型文を返す。"""
    clean_title, clean_body = _validated(title, body)
    resolved = _resolve_path(path)
    with _SNIPPETS_YAML_WRITE_LOCK:
        snippets = _load_for_update(resolved)
        if len(snippets) >= MAX_SNIPPETS:
            raise SnippetValidationError([f"定型文は{MAX_SNIPPETS}件まで登録できます"])
        existing = {s["id"] for s in snippets}
        sid = uuid.uuid4().hex[:12]
        while sid in existing:
            sid = uuid.uuid4().hex[:12]
        snippet = {"id": sid, "title": clean_title, "body": clean_body}
        snippets.append(snippet)
        _write(snippets, resolved)
    return snippet


def update_snippet(snippet_id: str, title: object, body: object, path: Path | None = None) -> dict:
    """定型文のタイトル・本文を更新し、更新後の定型文を返す（並び順は変えない）。"""
    clean_title, clean_body = _validated(title, body)
    resolved = _resolve_path(path)
    with _SNIPPETS_YAML_WRITE_LOCK:
        snippets = _load_for_update(resolved)
        for snippet in snippets:
            if snippet["id"] == snippet_id:
                snippet["title"] = clean_title
                snippet["body"] = clean_body
                _write(snippets, resolved)
                return dict(snippet)
    raise SnippetNotFoundError(snippet_id)


def delete_snippet(snippet_id: str, path: Path | None = None) -> list[dict]:
    """定型文を削除し、削除後の一覧を返す（ロック内で書いた内容をそのまま返す）。"""
    resolved = _resolve_path(path)
    with _SNIPPETS_YAML_WRITE_LOCK:
        snippets = _load_for_update(resolved)
        remaining = [s for s in snippets if s["id"] != snippet_id]
        if len(remaining) == len(snippets):
            raise SnippetNotFoundError(snippet_id)
        _write(remaining, resolved)
    return remaining


class SnippetOrderConflictError(SnippetValidationError):
    """並び替えの`ids`が現在の一覧と一致しない（画面の一覧が古い）。"""


def reorder_snippets(ids: object, path: Path | None = None) -> list[dict]:
    """`ids`の順に並べ替え、並べ替え後の一覧を返す。

    `ids`は現在の全定型文のidを過不足・重複なく含む必要がある。別画面で追加・削除
    された直後の古い一覧からの並べ替えで、定型文を取りこぼさないため。
    """
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise SnippetValidationError(["idsは文字列の配列である必要があります"])
    resolved = _resolve_path(path)
    with _SNIPPETS_YAML_WRITE_LOCK:
        snippets = _load_for_update(resolved)
        by_id = {s["id"]: s for s in snippets}
        if len(ids) != len(set(ids)) or set(ids) != set(by_id):
            raise SnippetOrderConflictError(
                ["定型文の一覧が最新ではありません。再読み込みしてから並べ替えてください"]
            )
        ordered = [by_id[i] for i in ids]
        _write(ordered, resolved)
    return ordered
