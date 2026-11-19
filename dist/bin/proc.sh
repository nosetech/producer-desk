# shellcheck shell=bash
# backend_*.sh / frontend_*.sh（issue #326、thoth等から個別に起動・停止するための
# スクリプト）が共有する処理。直接実行せず`source`して使う。一括起動の
# bin/start.sh / bin/stop.sh は挙動を変えないよう、このファイルは参照しない
# （PIDファイル・ログパス・環境変数はすべて一括スクリプトと同一）。
#
# 呼び出し側が事前に定義するもの: SCRIPT_TAG（メッセージ用）、ROOT_DIR

ORCHESTRATOR_DIR="${ROOT_DIR}/orchestrator"
DASHBOARD_DIR="${ROOT_DIR}/dashboard"
LOG_DIR="${ROOT_DIR}/logs"

ORCHESTRATOR_PID_FILE="${LOG_DIR}/orchestrator.pid"
DASHBOARD_PID_FILE="${LOG_DIR}/dashboard.pid"
ORCHESTRATOR_LOG="${LOG_DIR}/orchestrator.log"
DASHBOARD_LOG="${LOG_DIR}/dashboard.log"
ORCHESTRATOR_FALLBACK_LOG="${LOG_DIR}/orchestrator.stderr.log"

log() {
    echo "[${SCRIPT_TAG}] $*"
}

err() {
    echo "[${SCRIPT_TAG}] $*" >&2
}

# 標準入力を日次ローテーション付きで$1へ書き出すローテータ（bin/start.shと同じ。
# 配布物のルートで実行する）。
start_log_rotator() {
    cd "${ROOT_DIR}" || return 1
    exec nohup "${ORCHESTRATOR_DIR}/.venv/bin/python" -m orchestrator.log_rotator --path "$1" >/dev/null 2>&1
}

# $1=名前 $2=PIDファイル $3=止めるためのスクリプト名。
# launchd（bin/service.sh）登録済みの場合は二重起動になるため、呼び出し側で別途
# launchd_registered を確認すること。
check_not_running() {
    local name="$1" pid_file="$2" stop_script="$3"
    if [ -f "${pid_file}" ]; then
        local pid
        pid="$(cat "${pid_file}")"
        if kill -0 "${pid}" 2>/dev/null; then
            err "${name} は既に起動中です（PID ${pid}）。先に ./bin/${stop_script} を実行してください。"
            exit 1
        fi
        err "${name} の古いPIDファイルを検出しました（PID ${pid} は存在しません）。削除して続行します。"
        rm -f "${pid_file}"
    fi
}

# $1=orchestrator|dashboard。launchd登録済みなら案内して失敗させる。
reject_if_launchd() {
    if launchd_registered "$1"; then
        err "$1 は launchd（bin/service.sh）に登録済みです。./bin/service.sh status / restart で操作してください（手動起動したい場合は ./bin/service.sh stop または uninstall を先に実行してください）。"
        exit 1
    fi
}

# SIGTERM→最大10秒待機→SIGKILL。PIDファイルが無い／プロセスが無い場合は失敗
# （bin/stop.shと同じ扱い）。
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
