#!/bin/bash
# bin/litellm_proxy_start.sh で起動したLiteLLM Proxyを停止する。
#
# 使い方:
#   ./bin/litellm_proxy_stop.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PID_FILE="${REPO_ROOT}/logs/litellm_proxy.pid"

log() {
    echo "[litellm_proxy_stop] $*"
}

err() {
    echo "[litellm_proxy_stop] $*" >&2
}

if [ ! -f "${PID_FILE}" ]; then
    err "PIDファイルが見つかりません（起動していない可能性があります）: ${PID_FILE}"
    exit 1
fi

pid="$(cat "${PID_FILE}")"
if ! kill -0 "${pid}" 2>/dev/null; then
    err "プロセス（PID ${pid}）が見つかりません。PIDファイルを削除します。"
    rm -f "${PID_FILE}"
    exit 1
fi

log "LiteLLM Proxyを停止します（PID ${pid}）..."
kill "${pid}"
for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.5
done
if kill -0 "${pid}" 2>/dev/null; then
    err "プロセス（PID ${pid}）が停止しなかったため強制終了します"
    kill -9 "${pid}" 2>/dev/null || true
fi
rm -f "${PID_FILE}"
log "停止しました"
