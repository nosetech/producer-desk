"""orchestrator.attachments の単体テスト。HTTPアクセスはフェイクに差し替える。"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from email.message import Message

import pytest

from orchestrator.attachments import AttachmentError, fetch_attachment

ASSET_URL = "https://github.com/user-attachments/assets/07724aab-a5ec-4183-a942-845fccd103f1"
SIGNED_URL = "https://github-production-user-asset-6210df.s3.amazonaws.com/1/x.png?X-Amz=1"


class _Response(io.BytesIO):
    def __init__(self, data: bytes, headers: dict[str, str], status: int = 200) -> None:
        super().__init__(data)
        self.status = status
        self.headers = Message()
        for k, v in headers.items():
            self.headers[k] = v


def _redirect(location: str) -> urllib.error.HTTPError:
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError("u", 302, "Found", headers, None)


def _fake_open(responses: list):
    requests: list[urllib.request.Request] = []

    def open_fn(request: urllib.request.Request, timeout: float):
        requests.append(request)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return open_fn, requests


def test_fetch_follows_redirect_and_sends_token_only_to_first_hop() -> None:
    open_fn, requests = _fake_open(
        [_redirect(SIGNED_URL), _Response(b"png", {"Content-Type": "image/png"})]
    )

    response = fetch_attachment(ASSET_URL, token="ghp_x", open_fn=open_fn)

    assert response.status == 200
    assert response.headers == {"Content-Type": "image/png"}
    assert response.body.read() == b"png"
    assert requests[0].get_header("Authorization") == "Bearer ghp_x"
    assert requests[1].full_url == SIGNED_URL
    assert requests[1].get_header("Authorization") is None


def test_fetch_without_token_sends_no_authorization() -> None:
    open_fn, requests = _fake_open([_Response(b"x", {})])

    fetch_attachment(ASSET_URL, token=None, open_fn=open_fn)

    assert requests[0].get_header("Authorization") is None


def test_fetch_forwards_range_header() -> None:
    open_fn, requests = _fake_open([_Response(b"x", {"Content-Range": "bytes 0-0/9"}, 206)])

    response = fetch_attachment(ASSET_URL, token=None, range_header="bytes=0-0", open_fn=open_fn)

    assert requests[0].get_header("Range") == "bytes=0-0"
    assert response.status == 206


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/user-attachments/assets/07724aab-a5ec-4183-a942-845fccd103f1",
        "http://github.com/user-attachments/assets/07724aab-a5ec-4183-a942-845fccd103f1",
        "https://github.com/nosetech/producer-desk/issues/1",
        "https://github.com/user-attachments/assets/../../x",
    ],
)
def test_fetch_rejects_non_attachment_url(url: str) -> None:
    open_fn, requests = _fake_open([])

    with pytest.raises(AttachmentError) as e:
        fetch_attachment(url, token="ghp_x", open_fn=open_fn)

    assert e.value.status == 400
    assert requests == []


def test_fetch_accepts_files_url() -> None:
    open_fn, _ = _fake_open([_Response(b"x", {})])

    fetch_attachment(
        "https://github.com/user-attachments/files/123/a.txt", token=None, open_fn=open_fn
    )


def test_fetch_rejects_redirect_to_disallowed_host() -> None:
    open_fn, requests = _fake_open([_redirect("https://evil.example.com/x")])

    with pytest.raises(AttachmentError):
        fetch_attachment(ASSET_URL, token="ghp_x", open_fn=open_fn)

    assert len(requests) == 1


def test_fetch_propagates_http_error_status() -> None:
    error = urllib.error.HTTPError("u", 404, "Not Found", Message(), None)
    open_fn, _ = _fake_open([error])

    with pytest.raises(AttachmentError) as e:
        fetch_attachment(ASSET_URL, token="ghp_x", open_fn=open_fn)

    assert e.value.status == 404


def test_fetch_gives_up_after_too_many_redirects() -> None:
    open_fn, _ = _fake_open([_redirect(SIGNED_URL) for _ in range(10)])

    with pytest.raises(AttachmentError):
        fetch_attachment(ASSET_URL, token=None, open_fn=open_fn)
