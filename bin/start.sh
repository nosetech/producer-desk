#!/bin/bash
# dashboard・orchestratorを本番相当構成で一括起動する（運用インスタンス専用）。
# 既定ポート（orchestrator: 8787、dashboard: 3000）で起動する前提であり、
# 開発用インスタンスを別途並行起動する場合は README「リリース・日常運用」を参照。
#
# 使い方:
#   ./bin/start.sh
#
# 環境変数:
#   LAN_IP   同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#            `next start --hostname "$LAN_IP"` で起動する。未設定時は127.0.0.1のみ）
#   ORCHESTRATOR_PYTHON   orchestratorの起動に使うpythonインタプリタ
#            （既定: orchestrator/.venv/bin/python、無ければ python3）
#
# orchestrator/.env が存在する場合は起動前に読み込みexportする
# （SLACK_WEBHOOK_URL等、orchestrator/.env.example参照）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ORCHESTRATOR_DIR="${REPO_ROOT}/orchestrator"
DASHBOARD_DIR="${REPO_ROOT}/dashboard"
LOG_DIR="${REPO_ROOT}/logs"

ORCHESTRATOR_PID_FILE="${LOG_DIR}/orchestrator.pid"
DASHBOARD_PID_FILE="${LOG_DIR}/dashboard.pid"
ORCHESTRATOR_LOG="${LOG_DIR}/orchestrator.log"
DASHBOARD_LOG="${LOG_DIR}/dashboard.log"

log() {
    echo "[start] $*"
}

err() {
    echo "[start] $*" >&2
}

# 既に起動中の場合の二重起動防止。古いPIDファイルが残っているだけ（プロセスは
# 存在しない）場合は削除して続行する。
check_not_running() {
    local name="$1" pid_file="$2"
    if [ -f "${pid_file}" ]; then
        local pid
        pid="$(cat "${pid_file}")"
        if kill -0 "${pid}" 2>/dev/null; then
            err "${name} は既に起動中です（PID ${pid}）。先に ./bin/stop.sh を実行してください。"
            exit 1
        fi
        err "${name} の古いPIDファイルを検出しました（PID ${pid} は存在しません）。削除して続行します。"
        rm -f "${pid_file}"
    fi
}

check_not_running "orchestrator" "${ORCHESTRATOR_PID_FILE}"
check_not_running "dashboard" "${DASHBOARD_PID_FILE}"

mkdir -p "${LOG_DIR}"

if [ -f "${ORCHESTRATOR_DIR}/.env" ]; then
    log "orchestrator/.env を読み込みます"
    set -a
    # shellcheck disable=SC1091
    source "${ORCHESTRATOR_DIR}/.env"
    set +a
fi

if [ -z "${ORCHESTRATOR_PYTHON:-}" ]; then
    if [ -x "${ORCHESTRATOR_DIR}/.venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/.venv/bin/python"
    elif [ -x "${ORCHESTRATOR_DIR}/venv/bin/python" ]; then
        ORCHESTRATOR_PYTHON="${ORCHESTRATOR_DIR}/venv/bin/python"
    else
        ORCHESTRATOR_PYTHON="python3"
    fi
fi

NEXT_BIN="${DASHBOARD_DIR}/node_modules/.bin/next"
if [ ! -x "${NEXT_BIN}" ]; then
    err "dashboard/node_modules/.bin/next が見つかりません。先に \`cd dashboard && npm install\` を実行してください。"
    exit 1
fi

log "dashboard をビルドします..."
(cd "${DASHBOARD_DIR}" && npm run build)

log "orchestrator を起動します（${ORCHESTRATOR_PYTHON}）..."
(
    cd "${ORCHESTRATOR_DIR}"
    nohup "${ORCHESTRATOR_PYTHON}" -m orchestrator.main >>"${ORCHESTRATOR_LOG}" 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "dashboard を起動します..."
(
    cd "${DASHBOARD_DIR}"
    if [ -n "${LAN_IP:-}" ]; then
        nohup "${NEXT_BIN}" start --hostname "${LAN_IP}" >>"${DASHBOARD_LOG}" 2>&1 &
    else
        nohup "${NEXT_BIN}" start >>"${DASHBOARD_LOG}" 2>&1 &
    fi
    echo $! >"${DASHBOARD_PID_FILE}"
)

log "起動完了"
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG}"
log "  dashboard:    PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
if [ -n "${LAN_IP:-}" ]; then
    log "  dashboard URL: http://${LAN_IP}:3000"
else
    log "  dashboard URL: http://127.0.0.1:3000"
fi
log "停止する場合は ./bin/stop.sh を実行してください。"
