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
#   ORCHESTRATOR_PORT   orchestratorのbindポート（既定: 8787）。dashboardの
#                       接続先（ORCHESTRATOR_URL）はこのポートに自動追従する
#   ORCHESTRATOR_URL    dashboardからorchestratorへの接続先URL（既定:
#                       http://127.0.0.1:${ORCHESTRATOR_PORT}）。dashboard/.env
#                       で明示指定されている場合はそちらが優先される
#   DASHBOARD_PORT      dashboardのbindポート（既定: 3000）
#   LAN_IP              同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#                       `next start --hostname "$LAN_IP"` で起動する。未設定時は
#                       全インターフェースで待ち受ける既定動作のまま）
#   TAILSCALE_IP        外出先からTailscale経由でアクセスする場合のみ設定する
#                       （dashboardを`next start --hostname "$TAILSCALE_IP"`で
#                       起動する。`tailscale ip -4`で確認できる自機のTailscale
#                       IP。LAN_IPとは同時に指定できない）
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

# orchestrator.pyのlogging（JstMidnightRotatingFileHandler）が${ORCHESTRATOR_LOG}を
# 直接管理する（issue #114、orchestrator/orchestrator/logging_config.py参照）。
# 本体のstdout/stderrを同じパスへ`>>`でリダイレクトすると、日次ローテーション
# （rename後に開き直し）の後もシェルのfdが旧inodeを掴んだままになり、新しいログ
# に書かれないばかりか、backupCount超過で削除されたファイルの実体も解放されず
# 肥大化が再発する。そのためシェルの`>>`は使わず、本体の出力を
# orchestrator/orchestrator/log_rotator.py（issue #254）へパイプし、ローテータ
# 自身がファイルを開き直す方式にしている。
#   - orchestrator.stderr.log: configure_logging()前のクラッシュ・未捕捉例外の
#     トレースバックなど、ロガーを経由しない出力のフォールバック
#   - dashboard.log: Next.jsのstdout/stderr
# いずれも${ORCHESTRATOR_LOG}と同じく日次ローテーション・log_retention_days世代
# 保持（JST基準）。PIDファイルには本体のPIDを記録する（プロセス置換の`$!`は本体を
# 指す）。本体が終了するとパイプがEOFになり、ローテータも自然に終了する。
ORCHESTRATOR_FALLBACK_LOG="${LOG_DIR}/orchestrator.stderr.log"

# 標準入力を日次ローテーション付きで$1へ書き出すローテータ（orchestratorと同じ
# 保持日数設定を読むため、venvのpythonで実行する）。標準入出力以外は本体と切り
# 離す。
start_log_rotator() {
    cd "${ORCHESTRATOR_DIR}" || return 1
    exec nohup "${ORCHESTRATOR_PYTHON}" -m orchestrator.log_rotator --path "$1" >/dev/null 2>&1
}

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
# dashboard/.envでORCHESTRATOR_URLが明示指定されていればそちらを優先する
# （上のdashboard/.env読み込みの後にこの行を置くことで、シェルの既定値展開
# （未設定時のみ代入）がその指定を上書きしないようにしている）。
: "${ORCHESTRATOR_URL:=http://127.0.0.1:${ORCHESTRATOR_PORT}}"
export ORCHESTRATOR_PORT DASHBOARD_PORT ORCHESTRATOR_URL

# dashboardのbind先。`next start`の--hostnameは1つのアドレスしか取れないため、
# LAN_IPとTAILSCALE_IPの同時指定は曖昧になる。黙ってどちらかを選ばず明示的に失敗
# させる（両方から到達させたい場合は、どちらも未設定にして全インターフェースで
# 待ち受ける既定動作を使う）。
if [ -n "${LAN_IP:-}" ] && [ -n "${TAILSCALE_IP:-}" ]; then
    err "LAN_IP と TAILSCALE_IP は同時に指定できません。どちらか一方のみ設定してください（両方から到達させたい場合は両方とも未設定にしてください）。"
    exit 1
fi
DASHBOARD_BIND_HOST="${TAILSCALE_IP:-${LAN_IP:-}}"

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
    PYTHONUNBUFFERED=1 nohup "${ORCHESTRATOR_PYTHON}" -m orchestrator.main \
        > >(start_log_rotator "${ORCHESTRATOR_FALLBACK_LOG}") 2>&1 &
    echo $! >"${ORCHESTRATOR_PID_FILE}"
)

log "dashboard を起動します（ポート${DASHBOARD_PORT}）..."
(
    cd "${DASHBOARD_DIR}"
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
log "  orchestrator: PID $(cat "${ORCHESTRATOR_PID_FILE}")  log: ${ORCHESTRATOR_LOG} (fallback: ${ORCHESTRATOR_FALLBACK_LOG})  URL: http://127.0.0.1:${ORCHESTRATOR_PORT}"
log "  dashboard:    PID $(cat "${DASHBOARD_PID_FILE}")  log: ${DASHBOARD_LOG}"
if [ -n "${DASHBOARD_BIND_HOST}" ]; then
    log "  dashboard URL: http://${DASHBOARD_BIND_HOST}:${DASHBOARD_PORT}"
else
    log "  dashboard URL: http://127.0.0.1:${DASHBOARD_PORT}"
fi
log "停止する場合は ./bin/stop.sh を実行してください。"
