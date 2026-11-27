"""ダッシュボードから送られた画像・動画添付の検証・一時保存・後片付け（issue #301）。

仕様: docs/basic-design.md 2-4-1「ダッシュボードからの画像・動画添付」

- 添付はJSONの`attachments: [{name, mimeType, dataBase64}]`で受け取る（オーケストレータは
  標準ライブラリの`http.server`で動いており、multipartのパーサを持たないため）
- 形式は`gh --attach`で付けられる画像（png/jpg/jpeg/gif）・動画（mp4/mov/webm）に限る。
  svgは`gh`では付けられるが、スクリプトを含められる（XSS）ため除外する
- 形式は拡張子とマジックバイトの両方で確かめる
- 保存先はworktreeの外（`config/media_uploads/`、`.gitignore`対象）。ファイル名はサーバ側で
  採番し、クライアントのファイル名はパスに使わない
- 正本はGitHubの`user-attachments`。ローカルのファイルは`gh --attach`とAgent Runnerに
  渡すための一時ファイルで、Agent Runnerの実行が終わったら削除する。取り残しは起動時に掃除する
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import REPO_ROOT

logger = logging.getLogger(__name__)

# 上限（gh・GitHubの制約に合わせる。動画は無料プランの上限10MBに合わせる）。
# ダッシュボード側の`dashboard/src/lib/mediaAttach.ts`と同じ値にすること。
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 10
MAX_ATTACHMENTS_TOTAL_BYTES = 50 * 1024 * 1024
# 添付付きリクエスト全体の上限（Content-Length）。base64で約4/3倍に膨らむ分と本文の余裕を見込む。
MAX_ATTACH_REQUEST_BYTES = MAX_ATTACHMENTS_TOTAL_BYTES * 4 // 3 + 1024 * 1024
# 取り残した一時ファイルを起動時に掃除する際の保持期間。
STALE_UPLOAD_DAYS = 7

DEFAULT_UPLOADS_DIR = REPO_ROOT / "config" / "media_uploads"
UPLOADS_DIR_ENV = "MEDIA_UPLOADS_DIR"

# Agent Runnerへのメッセージ末尾に追記するブロックの見出し。後片付けでこの見出し以降の
# 行からパスを取り出すため、文言を変える場合は`extract_attachment_paths`も合わせる。
ATTACHMENT_PATHS_HEADING = "添付ファイル（Readツールで確認できます）:"
_PATH_LINE = re.compile(r"^- .+ → (?P<path>/.+)$")

GH_ATTACH_REQUIRED_ERROR = (
    "このホストのghコマンドがv2.99.0未満のため、画像・動画の添付は送信できません。"
    "ghをアップデートしてください（テキストだけの送信はできます）"
)


class MediaAttachmentError(ValueError):
    """添付が不正（形式・中身・サイズ・件数）な場合に送出する。server.pyで400にする。"""


def _is_mp4_family(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp"


def _is_mov(data: bytes) -> bool:
    # QuickTimeは`ftyp qt  `のほか、古い形式では先頭ボックスが`moov`/`mdat`/`wide`/`free`等。
    return _is_mp4_family(data) or (
        len(data) >= 8 and data[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")
    )


# 拡張子 → (正規化した拡張子, マジックバイト判定)
_FORMATS: dict[str, tuple[str, Callable[[bytes], bool]]] = {
    "png": ("png", lambda d: d.startswith(b"\x89PNG\r\n\x1a\n")),
    "jpg": ("jpg", lambda d: d.startswith(b"\xff\xd8\xff")),
    "jpeg": ("jpg", lambda d: d.startswith(b"\xff\xd8\xff")),
    "gif": ("gif", lambda d: d.startswith((b"GIF87a", b"GIF89a"))),
    "mp4": ("mp4", _is_mp4_family),
    "mov": ("mov", _is_mov),
    "webm": ("webm", lambda d: d.startswith(b"\x1a\x45\xdf\xa3")),
}

ALLOWED_EXTENSIONS = tuple(_FORMATS)


@dataclass(frozen=True)
class DecodedAttachment:
    name: str
    ext: str
    data: bytes


@dataclass(frozen=True)
class SavedAttachment:
    name: str
    path: Path


def _display_name(name: object) -> str:
    """表示・ログ用のファイル名（パスには使わない）。改行等の制御文字は除く。"""
    if not isinstance(name, str) or not name.strip():
        return "attachment"
    cleaned = "".join(c for c in name.strip() if c.isprintable())
    return (cleaned or "attachment")[:200]


def decode_attachments(raw: object) -> list[DecodedAttachment]:
    """リクエストの`attachments`を検証・デコードする。未指定・空なら空リスト。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise MediaAttachmentError("attachmentsは配列で指定してください")
    if len(raw) > MAX_ATTACHMENTS:
        raise MediaAttachmentError(f"添付は1回{MAX_ATTACHMENTS}件までです（{len(raw)}件）")
    decoded: list[DecodedAttachment] = []
    total = 0
    for item in raw:
        if not isinstance(item, dict):
            raise MediaAttachmentError("attachmentsの要素はオブジェクトで指定してください")
        name = _display_name(item.get("name"))
        data_b64 = item.get("dataBase64")
        if not isinstance(data_b64, str) or not data_b64:
            raise MediaAttachmentError(f"{name}: dataBase64がありません")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        fmt = _FORMATS.get(ext)
        if fmt is None:
            raise MediaAttachmentError(f"{name}: 対応していない形式です")
        # base64のままでも上限超過は分かるので、デコード前に弾く（巨大な入力のデコードを避ける）。
        if len(data_b64) * 3 // 4 > MAX_ATTACHMENT_BYTES + 3:
            raise MediaAttachmentError(f"{name}: 1ファイル10MBを超えています")
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError) as e:
            raise MediaAttachmentError(f"{name}: base64として不正です") from e
        if not data:
            raise MediaAttachmentError(f"{name}: 空のファイルです")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise MediaAttachmentError(f"{name}: 1ファイル10MBを超えています")
        norm_ext, check = fmt
        if not check(data):
            raise MediaAttachmentError(f"{name}: ファイルの中身が拡張子（.{ext}）と一致しません")
        total += len(data)
        if total > MAX_ATTACHMENTS_TOTAL_BYTES:
            raise MediaAttachmentError("添付の合計が50MBを超えています")
        decoded.append(DecodedAttachment(name=name, ext=norm_ext, data=data))
    return decoded


def uploads_dir() -> Path:
    return Path(os.environ.get(UPLOADS_DIR_ENV, str(DEFAULT_UPLOADS_DIR)))


def save_attachments(
    repo: str,
    issue_key: str,
    attachments: list[DecodedAttachment],
    *,
    base_dir: Path | None = None,
) -> list[SavedAttachment]:
    """`<base>/<owner>__<name>/<issue_key>/<uuid>.<ext>`に保存する。

    `issue_key`はissue番号（新規作成ではissue番号確定前のため`new-<uuid>`）。
    """
    owner, name = repo.split("/", 1)
    safe = re.compile(r"[^A-Za-z0-9._-]")
    directory = (
        (base_dir or uploads_dir())
        / f"{safe.sub('_', owner)}__{safe.sub('_', name)}"
        / safe.sub("_", issue_key)
    )
    directory.mkdir(parents=True, exist_ok=True)
    saved: list[SavedAttachment] = []
    for att in attachments:
        path = (directory / f"{uuid.uuid4().hex}.{att.ext}").resolve()
        path.write_bytes(att.data)
        saved.append(SavedAttachment(name=att.name, path=path))
    return saved


def append_attachment_paths(message: str, saved: list[SavedAttachment]) -> str:
    """Agent Runnerへ渡すメッセージの末尾にだけ、添付のローカルパスを追記する。

    Privateリポジトリの`user-attachments`のURLは認証が無いと取得できないため、AIには
    ローカルのファイルを読ませる。GitHubのコメント本文には入れない。
    """
    if not saved:
        return message
    lines = [f"- {s.name} → {s.path}" for s in saved]
    block = "\n".join([ATTACHMENT_PATHS_HEADING, *lines])
    return f"{message}\n\n{block}" if message else block


def extract_attachment_paths(message: str) -> list[Path]:
    """`append_attachment_paths`で追記したパスを取り出す（後片付け用）。"""
    _, sep, tail = message.rpartition(ATTACHMENT_PATHS_HEADING)
    if not sep:
        return []
    paths: list[Path] = []
    for line in tail.splitlines():
        match = _PATH_LINE.match(line.strip())
        if match:
            paths.append(Path(match.group("path")))
    return paths


def remove_saved(paths: list[Path], *, base_dir: Path | None = None) -> None:
    """一時ファイルを削除する。保存先ディレクトリ配下以外のパスは触らない。

    削除後に空になったissueディレクトリも消す。失敗はログに留める。
    """
    root = (base_dir or uploads_dir()).resolve()
    for path in paths:
        try:
            resolved = path.resolve()
            if root not in resolved.parents:
                logger.warning("添付の保存先外のパスは削除しません: %s", path)
                continue
            resolved.unlink(missing_ok=True)
            parent = resolved.parent
            if parent != root and not any(parent.iterdir()):
                parent.rmdir()
        except OSError as e:
            logger.warning("添付の一時ファイルを削除できませんでした (%s): %s", path, e)


def cleanup_after_run(message: str, *, base_dir: Path | None = None) -> None:
    """Agent Runnerの実行終了後（成否を問わず）に、そのメッセージの添付を削除する。"""
    paths = extract_attachment_paths(message)
    if paths:
        remove_saved(paths, base_dir=base_dir)


def cleanup_stale_uploads(
    *,
    base_dir: Path | None = None,
    max_age_days: float = STALE_UPLOAD_DAYS,
    now: float | None = None,
) -> int:
    """異常終了などで取り残した一時ファイルのうち、保持期間を過ぎたものを削除する（起動時）。"""
    root = base_dir or uploads_dir()
    if not root.is_dir():
        return 0
    threshold = (now if now is not None else time.time()) - max_age_days * 86400
    removed = 0
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if path.is_file() and path.stat().st_mtime < threshold:
                path.unlink()
                removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                shutil.rmtree(path, ignore_errors=True)
        except OSError as e:
            logger.warning("古い添付の一時ファイルを削除できませんでした (%s): %s", path, e)
    return removed
