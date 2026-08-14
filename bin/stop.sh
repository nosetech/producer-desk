#!/bin/bash
# bin/start.sh で起動したdashboard・orchestratorを停止する。
#
# 使い方:
#   ./bin/stop.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_DIR="${REPO_ROOT}/logs"
ORCHESTRATOR_PID_FILE="${LOG_DIR}/orchestrator.pid"
DASHBOARD_PID_FILE="${LOG_DIR}/dashboard.pid"

log() {
    echo "[stop] $*"
}

err() {
    echo "[stop] $*" >&2
}

# 停止対象プロセスが見つからない場合は失敗として扱う（呼び出し元でexit statusを見る）。
stop_process() {
    local name="$1" pid_file="$2"

    if [ ! -f "${pid_file}" ]; then
        err "${name} のPIDファイルが見つかりません（起動していない可能性があります）: ${pid_file}"
        return 1
    fi

    local pid
    pid="$(cat "${pid_file}")"
    if ! kill -0 "${pid}" 2>/dev/null; then
        err "${name} のプロセス（PID ${pid}）が見つかりません。PIDファイルを削除します。"
        rm -f "${pid_file}"
        return 1
    fi

    log "${name} を停止します（PID ${pid}）..."
    kill "${pid}"
    for _ in $(seq 1 20); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "${pid}" 2>/dev/null; then
        err "${name}（PID ${pid}）が停止しなかったため強制終了します"
        kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
    log "${name} を停止しました"
}

status=0
stop_process "orchestrator" "${ORCHESTRATOR_PID_FILE}" || status=1
stop_process "dashboard" "${DASHBOARD_PID_FILE}" || status=1

exit "${status}"
