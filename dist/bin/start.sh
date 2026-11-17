#!/bin/bash
# 配布パッケージ（GitHub Releasesのtarball、SETUP.md参照）内のdashboard・
# orchestratorを一括起動する。git clone前提の開発用bin/start.shとは異なり、
# ビルド済みのdashboard（Next.js standalone出力）・orchestrator（wheel
# インストール済みの仮想環境）をそのまま起動するだけで、npm install/npm run
# build・pip install -e等のソースビルドは一切行わない。
#
# 使い方:
#   ./bin/start.sh
#
# 初回起動時、orchestrator/.venv が無ければ自動的に作成し、同梱の
# orchestrator/dist/*.whl をインストールしてから起動する。
#
# ポート・LAN公開設定・Slack通知等は環境変数で上書きできる。シェルでの
# exportに加えて、展開先ルートに .env（.env.example参照）を作成しておけば
# このスクリプトが起動時に読み込む。
#
#   ORCHESTRATOR_PORT   orchestratorのbindポート（既定: 8787）。dashboardの
#                       接続先（ORCHESTRATOR_URL）はこのポートに自動追従する
#   ORCHESTRATOR_URL    dashboardからorchestratorへの接続先URL（既定:
#                       http://127.0.0.1:${ORCHESTRATOR_PORT}）。dashboardのみ
#                       別ホスト・別ポートのorchestratorに向けたい場合にのみ
#                       明示的に指定する
#   DASHBOARD_PORT      dashboardのbindポート（既定: 3000）
#   LAN_IP              同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#                       そのLAN IPでbindする。未設定時は全インターフェースで
#                       待ち受ける既定動作のまま）
#   TAILSCALE_IP        外出先からTailscale経由でアクセスする場合のみ設定する
#                       （dashboardをそのTailscale IPでbindする。`tailscale ip -4`
#                       で確認できる自機のTailscale IP。LAN_IPとは同時に指定
#                       できない）
#   SLACK_WEBHOOK_URL   判断待ち・レビュー待ち発生時のSlack通知先。未設定の
#                       場合、通知処理は単にスキップされる（起動エラーには
#                       ならない）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ORCHESTRATOR_DIR="${ROOT_DIR}/orchestrator"
DASHBOARD_DIR="${ROOT_DIR}/dashboard"
LOG_DIR="${ROOT_DIR}/logs"

ORCHESTRATOR_PID_FILE="${LOG_DIR}/orchestrator.pid"
DASHBOARD_PID_FILE="${LOG_DIR}/dashboard.pid"
ORCHESTRATOR_LOG="${LOG_DIR}/orchestrator.log"
DASHBOARD_LOG="${LOG_DIR}/dashboard.log"

# orchestrator.pyのlogging（JstMidnightRotatingFileHandler）が${ORCHESTRATOR_LOG}を
# 直接管理する。本体のstdout/stderrをシェルの`>>`でファイルへ向けると、日次
# ローテーション（rename）後も旧inodeへ書き続け肥大化するため、出力は
# orchestrator.log_rotator（日次ローテーション・log_retention_days世代保持・JST
# 基準）へパイプする（開発用bin/start.shと同じ設計、詳細はそちらのコメントおよび
# producer-desk本体issue #114・#254参照）。PIDファイルには本体のPIDを記録する。
ORCHESTRATOR_FALLBACK_LOG="${LOG_DIR}/orchestrator.stderr.log"

# 標準入力を日次ローテーション付きで$1へ書き出すローテータ。wheel版のREPO_ROOTは
# カレントディレクトリ基準のため、配布物のルートで実行する。
start_log_rotator() {
    cd "${ROOT_DIR}" || return 1
    exec nohup "${ORCHESTRATOR_DIR}/.venv/bin/python" -m orchestrator.log_rotator --path "$1" >/dev/null 2>&1
}

log() {
    echo "[start] $*"
}

err() {
    echo "[start] $*" >&2
}

# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

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

# launchd（bin/service.sh）で常時起動を登録済みの場合は二重起動になるため拒否する
for _svc in orchestrator dashboard; do
    if launchd_registered "${_svc}"; then
        err "${_svc} は launchd（bin/service.sh）に登録済みです。./bin/service.sh status / restart で操作してください（手動起動したい場合は ./bin/service.sh stop または uninstall を先に実行してください）。"
        exit 1
    fi
done

check_not_running "orchestrator" "${ORCHESTRATOR_PID_FILE}"
check_not_running "dashboard" "${DASHBOARD_PID_FILE}"

mkdir -p "${LOG_DIR}"

load_config || exit 1
ensure_orchestrator_venv || exit 1

if [ ! -f "${DASHBOARD_DIR}/server.js" ]; then
    err "dashboard/server.js が見つかりません。配布パッケージが破損している可能性があります。"
    exit 1
fi

log "orchestrator を起動します（ポート${ORCHESTRATOR_PORT}）..."
(
    cd "${ROOT_DIR}"
    PYTHONUNBUFFERED=1 nohup "${ORCHESTRATOR_DIR}/.venv/bin/orchestrator" \
        > >(start_log_rotator "${ORCHESTRATOR_FALLBACK_LOG}") 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "dashboard を起動します（ポート${DASHBOARD_PORT}）..."
(
    cd "${DASHBOARD_DIR}"
    export NODE_ENV=production
    export PORT="${DASHBOARD_PORT}"
    export ORCHESTRATOR_URL
    if [ -n "${DASHBOARD_BIND_HOST}" ]; then
        export HOSTNAME="${DASHBOARD_BIND_HOST}"
    fi
    nohup node server.js > >(start_log_rotator "${DASHBOARD_LOG}") 2>&1 &
    echo $! >"${DASHBOARD_PID_FILE}"
)

log "起動完了"
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG} (fallback: ${ORCHESTRATOR_FALLBACK_LOG})  URL: http://127.0.0.1:${ORCHESTRATOR_PORT}"
log "  dashboard:    PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
if [ -n "${DASHBOARD_BIND_HOST}" ]; then
    log "  dashboard URL: http://${DASHBOARD_BIND_HOST}:${DASHBOARD_PORT}"
else
    log "  dashboard URL: http://127.0.0.1:${DASHBOARD_PORT}"
fi
log "停止する場合は ./bin/stop.sh を実行してください。"
