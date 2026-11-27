#!/bin/bash
# dashboard（フロントエンド）のみを起動する（配布パッケージ用、issue #326）。
# bin/start.sh の dashboard 部分だけを切り出したもの。PIDファイル・ログ・環境変数
# （展開先ルートの .env 含む）は bin/start.sh と同一のため、bin/stop.sh でも停止できる。
# 配布版はビルド済み（Next.js standalone）のため、開発版のようなビルド省略オプションは無い。
#
# 使い方:
#   ./bin/frontend_start.sh
#
# バックグラウンドで起動してすぐ終了する（PIDは logs/dashboard.pid に記録）。
# 既に起動中なら失敗する。launchd（bin/service.sh）登録中は併用できず失敗する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="frontend_start"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

reject_if_launchd dashboard
check_not_running "dashboard" "${DASHBOARD_PID_FILE}" "frontend_stop.sh"

mkdir -p "${LOG_DIR}"

load_config || exit 1
# ps上のプロセス名（issue #332）。空文字を明示した場合は上書きしない（nodeのまま）
# ため、:= ではなく = で未設定時のみ既定値にする。
: "${DASHBOARD_PROCESS_NAME=producer-desk-dashboard}"
# ログローテータはorchestratorのvenvのpythonで動かすため、venvが必要（bin/start.shと同じ）
ensure_orchestrator_venv || exit 1

if [ ! -f "${DASHBOARD_DIR}/server.js" ]; then
    err "dashboard/server.js が見つかりません。配布パッケージが破損している可能性があります。"
    exit 1
fi

log "dashboard を起動します（ポート${DASHBOARD_PORT}）..."
(
    cd "${DASHBOARD_DIR}"
    export NODE_ENV=production
    export PORT="${DASHBOARD_PORT}"
    export ORCHESTRATOR_URL
    if [ -n "${DASHBOARD_BIND_HOST}" ]; then
        export HOSTNAME="${DASHBOARD_BIND_HOST}"
    fi
    if [ -n "${DASHBOARD_PROCESS_NAME}" ] && [ -f "${SCRIPT_DIR}/set_process_title.cjs" ]; then
        # Next.jsが起動後にprocess.titleを固定名へ書き換えるため、事前読み込み
        # スクリプトで設定・上書き防止する。既存のNODE_OPTIONSには追記する。
        export PROCESS_TITLE="${DASHBOARD_PROCESS_NAME}"
        export NODE_OPTIONS="${NODE_OPTIONS:+${NODE_OPTIONS} }--require \"${SCRIPT_DIR}/set_process_title.cjs\""
    fi
    nohup node server.js > >(start_log_rotator "${DASHBOARD_LOG}") 2>&1 &
    echo $! >"${DASHBOARD_PID_FILE}"
)

log "起動完了"
log "  dashboard: PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
log "  dashboard URL: http://${DASHBOARD_BIND_HOST:-127.0.0.1}:${DASHBOARD_PORT}"
log "停止する場合は ./bin/frontend_stop.sh を実行してください。"
