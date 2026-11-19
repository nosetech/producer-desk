#!/bin/bash
# orchestrator（バックエンド）のみを起動する（配布パッケージ用、issue #326）。
# bin/start.sh の orchestrator 部分だけを切り出したもの。PIDファイル・ログ・環境変数
# （展開先ルートの .env 含む）は bin/start.sh と同一のため、bin/stop.sh でも停止できる。
#
# 使い方:
#   ./bin/backend_start.sh
#
# バックグラウンドで起動してすぐ終了する（PIDは logs/orchestrator.pid に記録）。
# 既に起動中なら失敗する。launchd（bin/service.sh）登録中は併用できず失敗する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="backend_start"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

reject_if_launchd orchestrator
check_not_running "orchestrator" "${ORCHESTRATOR_PID_FILE}" "backend_stop.sh"

mkdir -p "${LOG_DIR}"

load_config || exit 1
ensure_orchestrator_venv || exit 1

log "orchestrator を起動します（ポート${ORCHESTRATOR_PORT}）..."
(
    cd "${ROOT_DIR}"
    PYTHONUNBUFFERED=1 nohup "${ORCHESTRATOR_DIR}/.venv/bin/orchestrator" \
        > >(start_log_rotator "${ORCHESTRATOR_FALLBACK_LOG}") 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "起動完了"
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG} (fallback: ${ORCHESTRATOR_FALLBACK_LOG})  URL: http://127.0.0.1:${ORCHESTRATOR_PORT}"
log "停止する場合は ./bin/backend_stop.sh を実行してください。"
