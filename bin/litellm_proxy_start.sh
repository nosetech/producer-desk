#!/bin/bash
# LiteLLM Proxy（issue #148・#174・#176）をネイティブ構成（Docker不使用）で起動する。
#
# 使い方:
#   ./bin/litellm_proxy_start.sh
#
# config/projects.yamlのいずれかのプロジェクトでexecution_mode: litellm_proxyを
# 選ぶ場合にのみ必要（既定のclaude_codeのみを使う運用では起動不要）。
#
# 専用のvenv（litellm_proxy/.venv）に `litellm[proxy]` をインストールする
# （オーケストレータ本体のvenvとは分離する。litellm[proxy]は依存が重く、
# オーケストレータ本体のpyproject.tomlには追加しない）。カスタムコールバック
# （orchestrator/orchestrator/litellm_callback.py）がusage_store.py経由で
# config/usage.dbへ書き込むため、この専用venvへorchestratorパッケージも
# editable installし、LiteLLM Proxyプロセス自身がインポートできるようにする。
#
# 設定ファイルは config/litellm_config.yaml（config/litellm_config.yaml.example
# 参照、.gitignore対象）。
#
# ポート・接続先は環境変数で上書きできる（docs/basic-design.md 3-1・4章）。
#   LITELLM_PROXY_PORT   LiteLLM Proxyのbindポート（既定: 4000）
#   LITELLM_PROXY_URL    orchestrator（agent_runner.py）が接続する先のURL
#                        （既定: http://127.0.0.1:${LITELLM_PROXY_PORT}）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LITELLM_DIR="${REPO_ROOT}/litellm_proxy"
ORCHESTRATOR_DIR="${REPO_ROOT}/orchestrator"
LOG_DIR="${REPO_ROOT}/logs"
CONFIG_PATH="${REPO_ROOT}/config/litellm_config.yaml"

PID_FILE="${LOG_DIR}/litellm_proxy.pid"
LOG_FILE="${LOG_DIR}/litellm_proxy.log"

log() {
    echo "[litellm_proxy_start] $*"
}

err() {
    echo "[litellm_proxy_start] $*" >&2
}

if [ ! -f "${CONFIG_PATH}" ]; then
    err "設定ファイルが見つかりません: ${CONFIG_PATH}"
    err "config/litellm_config.yaml.example を参考に作成してください。"
    exit 1
fi

if [ -f "${PID_FILE}" ]; then
    pid="$(cat "${PID_FILE}")"
    if kill -0 "${pid}" 2>/dev/null; then
        err "LiteLLM Proxyは既に起動中です（PID ${pid}）。先に ./bin/litellm_proxy_stop.sh を実行してください。"
        exit 1
    fi
    err "古いPIDファイルを検出しました（PID ${pid} は存在しません）。削除して続行します。"
    rm -f "${PID_FILE}"
fi

mkdir -p "${LOG_DIR}"

if [ ! -x "${LITELLM_DIR}/.venv/bin/python" ]; then
    log "litellm_proxy/.venv が見つからないため作成します..."
    mkdir -p "${LITELLM_DIR}"
    python3 -m venv "${LITELLM_DIR}/.venv"
    "${LITELLM_DIR}/.venv/bin/pip" install 'litellm[proxy]'
    # カスタムコールバック（orchestrator.litellm_callback）がusage_store.py経由で
    # config/usage.dbへ書き込めるよう、orchestratorパッケージも同じvenvへ
    # editable installする。
    "${LITELLM_DIR}/.venv/bin/pip" install -e "${ORCHESTRATOR_DIR}"
fi

: "${LITELLM_PROXY_PORT:=4000}"
export LITELLM_PROXY_PORT

log "LiteLLM Proxyを起動します（ポート${LITELLM_PROXY_PORT}、設定: ${CONFIG_PATH}）..."
(
    cd "${REPO_ROOT}"
    nohup "${LITELLM_DIR}/.venv/bin/litellm" \
        --config "${CONFIG_PATH}" \
        --port "${LITELLM_PROXY_PORT}" \
        >>"${LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
)

log "起動完了: PID $(cat "${PID_FILE}")  log: ${LOG_FILE}  URL: http://127.0.0.1:${LITELLM_PROXY_PORT}"
log "停止する場合は ./bin/litellm_proxy_stop.sh を実行してください。"
