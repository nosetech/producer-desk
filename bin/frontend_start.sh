#!/bin/bash
# dashboard（フロントエンド）のみを起動する（開発環境・運用インスタンス向け、issue #326）。
# bin/start.sh の dashboard 部分だけを切り出したもの。PIDファイル・ログ・環境変数は
# bin/start.sh と同一のため、bin/stop.sh でも停止できる。
#
# 使い方:
#   ./bin/frontend_start.sh
#   SKIP_BUILD=1 ./bin/frontend_start.sh   # npm ci とビルドを省略して再起動だけ行う
#
# バックグラウンドで起動してすぐ終了する（PIDは logs/dashboard.pid に記録）。
# 既に起動中なら失敗する。環境変数（DASHBOARD_PORT・ORCHESTRATOR_URL・LAN_IP・
# TAILSCALE_IP・DASHBOARD_PROCESS_NAME）は bin/start.sh のヘッダ参照。
# SKIP_BUILD=1 は dashboard/.next と node_modules が既にある（直前に同じコードで
# ビルド済みの）場合のみ使える。コードを更新した後は付けずに実行すること。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="frontend_start"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"

check_not_running "dashboard" "${DASHBOARD_PID_FILE}" "frontend_stop.sh"

mkdir -p "${LOG_DIR}"
load_dev_env

: "${ORCHESTRATOR_PORT:=8787}"
: "${DASHBOARD_PORT:=3000}"
: "${ORCHESTRATOR_URL:=http://127.0.0.1:${ORCHESTRATOR_PORT}}"
export ORCHESTRATOR_PORT DASHBOARD_PORT ORCHESTRATOR_URL
# ps上のプロセス名（issue #332）。空文字を明示した場合は上書きしない（next-serverのまま）
# ため、:= ではなく = で未設定時のみ既定値にする。
: "${DASHBOARD_PROCESS_NAME=producer-desk-dashboard}"

if [ -n "${LAN_IP:-}" ] && [ -n "${TAILSCALE_IP:-}" ]; then
    err "LAN_IP と TAILSCALE_IP は同時に指定できません。どちらか一方のみ設定してください（両方から到達させたい場合は両方とも未設定にしてください）。"
    exit 1
fi
DASHBOARD_BIND_HOST="${TAILSCALE_IP:-${LAN_IP:-}}"

# ログローテータは orchestrator の venv の python で動かす（bin/start.sh と同じ）。
if [ -z "${ORCHESTRATOR_PYTHON:-}" ]; then
    if [ -x "${ORCHESTRATOR_DIR}/.venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/.venv/bin/python"
    elif [ -x "${ORCHESTRATOR_DIR}/venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/venv/bin/python"
    else
        log "orchestrator/.venv が見つからないため作成します（ログローテータ用）..."
        python3 -m venv "${ORCHESTRATOR_DIR}/.venv"
        "${ORCHESTRATOR_DIR}/.venv/bin/pip" install -e "${ORCHESTRATOR_DIR}"
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/.venv/bin/python"
    fi
fi

NEXT_BIN="${DASHBOARD_DIR}/node_modules/.bin/next"
export NODE_ENV=production

if [ "${SKIP_BUILD:-}" = "1" ]; then
    if [ ! -x "${NEXT_BIN}" ] || [ ! -d "${DASHBOARD_DIR}/.next" ]; then
        err "SKIP_BUILD=1 が指定されましたが dashboard/node_modules または dashboard/.next がありません。SKIP_BUILD を外して実行してください。"
        exit 1
    fi
    log "SKIP_BUILD=1 のため npm ci とビルドを省略します"
else
    # --include=dev の理由は bin/start.sh のコメント参照。
    log "dashboard の依存関係を package-lock.json と照合します（npm ci）..."
    (cd "${DASHBOARD_DIR}" && npm ci --include=dev)
    if [ ! -x "${NEXT_BIN}" ]; then
        err "npm ci 実行後も dashboard/node_modules/.bin/next が見つかりません。dashboard/package.json の内容を確認してください。"
        exit 1
    fi
    log "dashboard をビルドします..."
    (cd "${DASHBOARD_DIR}" && npm run build)
fi

log "dashboard を起動します（ポート${DASHBOARD_PORT}）..."
(
    cd "${DASHBOARD_DIR}"
    if [ -n "${DASHBOARD_PROCESS_NAME}" ]; then
        # Next.jsが起動後にprocess.titleを"next-server (v...)"へ固定で書き換えるため、
        # 事前読み込みスクリプトで設定・上書き防止する。既存のNODE_OPTIONSには追記する。
        export PROCESS_TITLE="${DASHBOARD_PROCESS_NAME}"
        export NODE_OPTIONS="${NODE_OPTIONS:+${NODE_OPTIONS} }--require \"${SCRIPT_DIR}/set_process_title.cjs\""
    fi
    if [ -n "${DASHBOARD_BIND_HOST}" ]; then
        nohup "${NEXT_BIN}" start -p "${DASHBOARD_PORT}" --hostname "${DASHBOARD_BIND_HOST}" \
            > >(start_log_rotator "${DASHBOARD_LOG}") 2>&1 &
    else
        nohup "${NEXT_BIN}" start -p "${DASHBOARD_PORT}" \
            > >(start_log_rotator "${DASHBOARD_LOG}") 2>&1 &
    fi
    echo $! >"${DASHBOARD_PID_FILE}"
)

log "起動完了"
log "  dashboard: PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
log "  dashboard URL: http://${DASHBOARD_BIND_HOST:-127.0.0.1}:${DASHBOARD_PORT}"
log "停止する場合は ./bin/frontend_stop.sh を実行してください。"
