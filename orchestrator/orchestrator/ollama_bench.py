"""LocalLLM（Ollama）の手動ベンチマークツール。Ollama REST APIを直接呼び出す。

MCP `ollama-client` はOllama REST APIレスポンスに含まれる`prompt_eval_count`/
`eval_count`/`total_duration`等のメトリクスをそのまま返さないため、正確な
トークン数・処理時間を計測するにはMCPを経由せずOllama REST API
（`POST /api/chat`, `stream: false`）に直接アクセスする必要がある
（issue #60コメント参照）。

このツールは人間が手動でモデル比較・性能検証を行う専用であり、Agent Runner
本番経路（MCP `ollama-client`経由、`agent_runner.AGENT_RUNNER_LOCAL_LLM_INSTRUCTION`）
は変更しない。
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orchestrator.usage_store import DEFAULT_USAGE_DB_PATH, UsageRecord
from orchestrator.usage_store import record_usage as store_record_usage

OLLAMA_HOST_ENV = "OLLAMA_HOST"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"

# (url, payload, timeout) -> レスポンスJSONをdictにdecodeしたもの。
# 実装は`_http_post`（urllib）だが、テストでは実ネットワークを叩かず差し替える
# （`agent_runner.RunFn`と同じDIパターン、docs/basic-design.md参照）。
HttpPostFn = Callable[..., dict]


@dataclass
class BenchmarkResult:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_duration_ns: int
    load_duration_ns: int
    prompt_eval_duration_ns: int
    eval_duration_ns: int
    response_text: str


def resolve_ollama_host(host: str | None = None) -> str:
    return host or os.environ.get(OLLAMA_HOST_ENV) or DEFAULT_OLLAMA_HOST


def _http_post(url: str, payload: bytes, *, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def call_ollama_chat(
    model: str,
    prompt: str,
    *,
    host: str | None = None,
    system: str | None = None,
    timeout: float = 300.0,
    http_post: HttpPostFn = _http_post,
) -> BenchmarkResult:
    """`POST /api/chat`（`stream: false`）を直接呼び出し、実測のトークン数・処理時間を取得する。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
    url = f"{resolve_ollama_host(host).rstrip('/')}/api/chat"
    body = http_post(url, payload, timeout=timeout)

    return BenchmarkResult(
        model=model,
        prompt_tokens=int(body.get("prompt_eval_count", 0) or 0),
        completion_tokens=int(body.get("eval_count", 0) or 0),
        total_duration_ns=int(body.get("total_duration", 0) or 0),
        load_duration_ns=int(body.get("load_duration", 0) or 0),
        prompt_eval_duration_ns=int(body.get("prompt_eval_duration", 0) or 0),
        eval_duration_ns=int(body.get("eval_duration", 0) or 0),
        response_text=(body.get("message") or {}).get("content", ""),
    )


def to_usage_record(result: BenchmarkResult, *, repo: str, issue_number: int) -> UsageRecord:
    """ベンチマーク結果を`usage_store`の記録スキーマに変換する（`config/usage.db`に統合）。"""
    return UsageRecord(
        repo=repo,
        issue_number=issue_number,
        model=result.model,
        input_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        duration_seconds=result.total_duration_ns / 1_000_000_000,
    )


def _seconds(duration_ns: int) -> float:
    return duration_ns / 1_000_000_000


def _print_result(result: BenchmarkResult) -> None:
    print(f"model: {result.model}")
    print(f"prompt_tokens (prompt_eval_count): {result.prompt_tokens}")
    print(f"completion_tokens (eval_count): {result.completion_tokens}")
    print(f"total_duration: {_seconds(result.total_duration_ns):.2f}s")
    print(f"load_duration: {_seconds(result.load_duration_ns):.2f}s")
    print(f"prompt_eval_duration: {_seconds(result.prompt_eval_duration_ns):.2f}s")
    print(f"eval_duration: {_seconds(result.eval_duration_ns):.2f}s")
    if result.eval_duration_ns > 0:
        tok_per_sec = result.completion_tokens / _seconds(result.eval_duration_ns)
        print(f"tok/s (eval): {tok_per_sec:.2f}")
    print("--- response ---")
    print(result.response_text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ollama REST APIを直接呼び出し、モデルのトークン数・処理時間を計測する"
            "手動ベンチマークツール（MCP ollama-clientでは取得できないメトリクス用）。"
        )
    )
    parser.add_argument("model", help="Ollamaモデル名（例: deepseek-coder-v2:16b）")
    parser.add_argument("prompt_file", type=Path, help="プロンプトを記載したテキストファイル")
    parser.add_argument("--system", default=None, help="systemメッセージ（任意）")
    parser.add_argument(
        "--host",
        default=None,
        help=f"Ollama REST APIのURL（未指定時は環境変数{OLLAMA_HOST_ENV}、"
        f"それも無ければ{DEFAULT_OLLAMA_HOST}）",
    )
    parser.add_argument(
        "--record", action="store_true", help=f"計測結果を{DEFAULT_USAGE_DB_PATH}に記録する"
    )
    parser.add_argument("--repo", default="", help="--record指定時、記録先のrepo（必須）")
    parser.add_argument(
        "--issue-number", type=int, default=0, help="--record指定時、記録先のissue番号"
    )
    args = parser.parse_args()

    if args.record and not args.repo:
        parser.error("--record指定時は--repoが必須です")

    prompt = args.prompt_file.read_text(encoding="utf-8")
    result = call_ollama_chat(args.model, prompt, host=args.host, system=args.system)
    _print_result(result)

    if args.record:
        store_record_usage(
            [to_usage_record(result, repo=args.repo, issue_number=args.issue_number)]
        )
        print(f"\n{DEFAULT_USAGE_DB_PATH} に記録しました（repo={args.repo}）")


if __name__ == "__main__":
    main()
