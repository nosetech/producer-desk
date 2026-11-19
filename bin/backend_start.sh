#!/bin/bash
# orchestrator（バックエンド）のみを起動する（開発環境・運用インスタンス向け、issue #326）。
# bin/start.sh の orchestrator 部分だけを切り出したもの。PIDファイル・ログ・環境変数は
# bin/start.sh と同一のため、bin/stop.sh でも停止できる。
#
# 使い方:
#   ./bin/backend_start.sh
#
# バックグラウンドで起動してすぐ終了する（PIDは logs/orchestrator.pid に記録）。
# 既に起動中なら失敗する。環境変数は bin/start.sh のヘッダ参照
# （ORCHESTRATOR_PORT・ORCHESTRATOR_PYTHON 等）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="backend_start"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"

check_not_running "orchestrator" "${ORCHESTRATOR_PID_FILE}" "backend_stop.sh"

mkdir -p "${LOG_DIR}"
load_dev_env

: "${ORCHESTRATOR_PORT:=8787}"
export ORCHESTRATOR_PORT

if [ -z "${ORCHESTRATOR_PYTHON:-}" ]; then
    if [ -x "${ORCHESTRATOR_DIR}/.venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/.venv/bin/python"
    elif [ -x "${ORCHESTRATOR_DIR}/venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/venv/bin/python"
    else
        log "orchestrator/.venv が見つからないため作成します..."
        python3 -m venv "${ORCHESTRATOR_DIR}/.venv"
        "${ORCHESTRATOR_DIR}/.venv/bin/pip" install -e "${ORCHESTRATOR_DIR}"
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/.venv/bin/python"
    fi
fi

log "orchestrator を起動します（${ORCHESTRATOR_PYTHON}、ポート${ORCHESTRATOR_PORT}）..."
(
    cd "${ORCHESTRATOR_DIR}"
    PYTHONUNBUFFERED=1 nohup "${ORCHESTRATOR_PYTHON}" -m orchestrator.main \
        > >(start_log_rotator "${ORCHESTRATOR_FALLBACK_LOG}") 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "起動完了"
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG} (fallback: ${ORCHESTRATOR_FALLBACK_LOG})  URL: http://127.0.0.1:${ORCHESTRATOR_PORT}"
log "停止する場合は ./bin/backend_stop.sh を実行してください。"
