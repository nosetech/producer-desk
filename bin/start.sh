#!/bin/bash
# dashboard・orchestratorを本番相当構成で一括起動する（運用インスタンス専用）。
# 開発用インスタンスを別途並行起動する場合は README「リリース・日常運用」を参照。
#
# 使い方:
#   ./bin/start.sh
#
# 起動のたびにdashboardの依存関係を`npm ci`でpackage-lock.jsonと照合・是正する
# （ネットワークアクセスが発生する。オフライン環境での起動には対応していない）。
#
# ポート・LAN公開設定は環境変数で上書きできる（shellでexportする方法に加えて、
# orchestrator/.env・dashboard/.env（それぞれの.env.example参照）でも指定可能）。
#
#   ORCHESTRATOR_PORT   orchestratorのbindポート（既定: 8787）
#   DASHBOARD_PORT      dashboardのbindポート（既定: 3000）
#   LAN_IP              同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#                       `next start --hostname "$LAN_IP"` で起動する。未設定時は
#                       全インターフェースで待ち受ける既定動作のまま）
#   ORCHESTRATOR_PYTHON   orchestratorの起動に使うpythonインタプリタ
#            （既定: orchestrator/.venv/bin/python。.venvが無ければこのスクリプトが
#            自動作成する。既にorchestrator/venv/bin/pythonがあればそちらを使う）
#
# logs/orchestrator.logの出力レベルは環境変数 ORCHESTRATOR_ENV で切り替えられる
# が、このスクリプトは明示的に設定しないため常に既定のproduction相当（INFO以上
# のみ出力）で起動する（開発時にDEBUG以上を見たい場合は`python -m
# orchestrator.main`を直接、ORCHESTRATOR_ENV=developmentを指定して起動すること。
# README「ログ出力先ディレクトリの運用方針」参照）。ローテーション保持日数は
# config/projects.yamlのlog_retention_days（既定7日）に従う。
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

if [ -f "${DASHBOARD_DIR}/.env" ]; then
    log "dashboard/.env を読み込みます"
    set -a
    # shellcheck disable=SC1091
    source "${DASHBOARD_DIR}/.env"
    set +a
fi

: "${ORCHESTRATOR_PORT:=8787}"
: "${DASHBOARD_PORT:=3000}"
export ORCHESTRATOR_PORT DASHBOARD_PORT

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

# --include=devを付けるのは、呼び出し元のシェルで既にNODE_ENV=productionが
# 設定されている場合、npmがdevDependencies（typescript等）を省略してインストール
# してしまい、後続のnext buildがtypescriptを検知できずに勝手に再インストールして
# package.json/package-lock.jsonを書き換えてしまうため。
log "dashboard の依存関係を package-lock.json と照合します（npm ci）..."
(cd "${DASHBOARD_DIR}" && npm ci --include=dev)
log "dashboard の依存関係の照合が完了しました"

NEXT_BIN="${DASHBOARD_DIR}/node_modules/.bin/next"
if [ ! -x "${NEXT_BIN}" ]; then
    err "npm ci 実行後も dashboard/node_modules/.bin/next が見つかりません。dashboard/package.json の内容を確認してください。"
    exit 1
fi

# 呼び出し元のシェルでNODE_ENVに"production"/"development"/"test"以外の値が
# 設定されていると、next buildが/_document関連の内部エラーで失敗することがある
# （vercel/next.js#77262等）。本番起動である以上、常にproductionへ固定する。
export NODE_ENV=production

log "dashboard をビルドします..."
(cd "${DASHBOARD_DIR}" && npm run build)

log "orchestrator を起動します（${ORCHESTRATOR_PYTHON}、ポート${ORCHESTRATOR_PORT}）..."
(
    cd "${ORCHESTRATOR_DIR}"
    nohup "${ORCHESTRATOR_PYTHON}" -m orchestrator.main >>"${ORCHESTRATOR_LOG}" 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "dashboard を起動します（ポート${DASHBOARD_PORT}）..."
(
    cd "${DASHBOARD_DIR}"
    if [ -n "${LAN_IP:-}" ]; then
        nohup "${NEXT_BIN}" start -p "${DASHBOARD_PORT}" --hostname "${LAN_IP}" >>"${DASHBOARD_LOG}" 2>&1 &
    else
        nohup "${NEXT_BIN}" start -p "${DASHBOARD_PORT}" >>"${DASHBOARD_LOG}" 2>&1 &
    fi
    echo $! >"${DASHBOARD_PID_FILE}"
)

log "起動完了"
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG}  URL: http://127.0.0.1:${ORCHESTRATOR_PORT}"
log "  dashboard:    PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
if [ -n "${LAN_IP:-}" ]; then
    log "  dashboard URL: http://${LAN_IP}:${DASHBOARD_PORT}"
else
    log "  dashboard URL: http://127.0.0.1:${DASHBOARD_PORT}"
fi
log "停止する場合は ./bin/stop.sh を実行してください。"
