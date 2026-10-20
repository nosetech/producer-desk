"""issueコメントの添付ファイル（画像・動画）のプロキシ取得。

`gh issue comment --attach`で添付されたファイルは
`https://github.com/user-attachments/assets/<uuid>`として本文に載る。このURLは
Publicリポジトリなら未ログインでも取得できるが、Privateリポジトリではブラウザが
GitHubにログインしていないと取得できない。そこで、ダッシュボードのブラウザからは
オーケストレータ経由（`GET /api/attachment`）で取得させ、サーバー側の
`config/projects.yaml`の`github_token`で認証してGitHubから取得する。

GitHubは認証済みリクエストを署名付きURL（S3等、約5分で失効）へ302でリダイレクトする。
`Authorization`ヘッダを署名付きURLへ引き継ぐとS3が拒否するため、リダイレクトは自前で
辿り、トークンは最初の`github.com`へのリクエストにのみ付与する。

仕様: docs/basic-design.md 2-4（添付ファイルの表示）
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO

logger = logging.getLogger(__name__)

# プロキシ対象として許可するURL（SSRF防止のため添付ファイルのURL形式のみ）。
ATTACHMENT_URL_PATTERN = re.compile(
    r"^https://github\.com/user-attachments/(?:assets/[0-9a-fA-F-]{36}|files/\d+/[^/?#]+)$"
)

# リダイレクト先として許可するホストのサフィックス（署名付きURLの配信元）。
_ALLOWED_REDIRECT_HOST_SUFFIXES = (".githubusercontent.com", ".amazonaws.com", ".github.com")
_MAX_REDIRECTS = 5
FETCH_TIMEOUT_SECONDS = 30.0


class AttachmentError(Exception):
    """添付ファイルを取得できなかった。`status`はダッシュボードへ返すHTTPステータス。"""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class AttachmentResponse:
    status: int
    headers: dict[str, str]
    body: IO[bytes]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


OpenFn = Callable[[urllib.request.Request, float], IO[bytes]]


def _default_open(request: urllib.request.Request, timeout: float) -> IO[bytes]:
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(request, timeout=timeout)


def _is_allowed_redirect(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and host.endswith(_ALLOWED_REDIRECT_HOST_SUFFIXES)


def fetch_attachment(
    url: str,
    *,
    token: str | None,
    range_header: str | None = None,
    open_fn: OpenFn = _default_open,
) -> AttachmentResponse:
    """添付ファイルを取得する。呼び出し側が`body`を読み終えたら閉じること。"""
    if not ATTACHMENT_URL_PATTERN.match(url):
        raise AttachmentError("添付ファイルのURLではありません", status=400)

    current = url
    for hop in range(_MAX_REDIRECTS + 1):
        headers = {"User-Agent": "producer-desk"}
        if hop == 0 and token:
            headers["Authorization"] = f"Bearer {token}"
        if range_header:
            headers["Range"] = range_header
        request = urllib.request.Request(current, headers=headers)
        try:
            response = open_fn(request, FETCH_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location")
                if not location:
                    raise AttachmentError("リダイレクト先が不明です") from e
                current = urllib.parse.urljoin(current, location)
                if not _is_allowed_redirect(current):
                    raise AttachmentError("許可されていないリダイレクト先です") from e
                continue
            # 404は存在しない、またはトークンに閲覧権限が無い場合（GitHubは権限不足を404で返す）。
            raise AttachmentError(f"GitHubが{e.code}を返しました", status=e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AttachmentError(f"GitHubに接続できません: {e}") from e

        status = getattr(response, "status", 200)
        passthrough = {
            name: value
            for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges")
            if (value := response.headers.get(name)) is not None
        }
        return AttachmentResponse(status=status, headers=passthrough, body=response)

    raise AttachmentError("リダイレクトが多すぎます")
