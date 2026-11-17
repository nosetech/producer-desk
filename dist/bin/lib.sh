# shellcheck shell=bash
# bin/start.sh と bin/service.sh が共有する設定読み込み・判定ロジック
# （issue #318）。直接実行せず `source` して使う。呼び出し側は以下を事前に
# 定義しておくこと。
#   ROOT_DIR / ORCHESTRATOR_DIR / DASHBOARD_DIR  展開先ルート等の絶対パス
#   log / err                                     メッセージ出力関数

SERVICE_LABEL_PREFIX="com.nosetech.producer-desk"

# .env読み込み・projects.yaml確認・ポート既定値・dashboardのbind先判定を行う。
# 結果は ORCHESTRATOR_PORT / DASHBOARD_PORT / ORCHESTRATOR_URL（export済み）と
# DASHBOARD_BIND_HOST に設定される。失敗時は非0を返す。
load_config() {
    if [ -f "${ROOT_DIR}/.env" ]; then
        log "${ROOT_DIR}/.env を読み込みます"
        set -a
        # shellcheck disable=SC1091
        source "${ROOT_DIR}/.env"
        set +a
    fi

    if [ ! -f "${ROOT_DIR}/config/projects.yaml" ]; then
        err "config/projects.yaml が見つかりません。SETUP.md の手順に従って config/projects.yaml.example から作成してください。"
        return 1
    fi

    : "${ORCHESTRATOR_PORT:=8787}"
    : "${DASHBOARD_PORT:=3000}"
    : "${ORCHESTRATOR_URL:=http://127.0.0.1:${ORCHESTRATOR_PORT}}"
    export ORCHESTRATOR_PORT DASHBOARD_PORT ORCHESTRATOR_URL

    # dashboardのbind先は1つのアドレスしか取れないため、LAN_IPとTAILSCALE_IPの同時
    # 指定は曖昧になる。黙ってどちらかを選ばず明示的に失敗させる（両方から到達させ
    # たい場合は、どちらも未設定にして全インターフェースで待ち受ける既定動作を使う）。
    if [ -n "${LAN_IP:-}" ] && [ -n "${TAILSCALE_IP:-}" ]; then
        err "LAN_IP と TAILSCALE_IP は同時に指定できません。どちらか一方のみ設定してください（両方から到達させたい場合は両方とも未設定にしてください）。"
        return 1
    fi
    # shellcheck disable=SC2034  # 呼び出し側（start.sh/service.sh）が参照する
    DASHBOARD_BIND_HOST="${TAILSCALE_IP:-${LAN_IP:-}}"
    return 0
}

# orchestrator/.venv が無ければ作成し、同梱wheelをインストールする。
ensure_orchestrator_venv() {
    if [ -x "${ORCHESTRATOR_DIR}/.venv/bin/orchestrator" ]; then
        return 0
    fi
    log "orchestrator/.venv が見つからないため作成します..."
    python3 -m venv "${ORCHESTRATOR_DIR}/.venv"
    local wheel_file
    wheel_file="$(ls "${ORCHESTRATOR_DIR}"/dist/*.whl 2>/dev/null | head -n1 || true)"
    if [ -z "${wheel_file}" ]; then
        err "orchestrator/dist/*.whl が見つかりません。配布パッケージが破損している可能性があります。"
        return 1
    fi
    "${ORCHESTRATOR_DIR}/.venv/bin/pip" install "${wheel_file}"
}

# launchdに $1（orchestrator|dashboard）が登録済み（bootstrap済み）なら0を返す。
# launchctlが無い環境（macOS以外）では常に1。
launchd_registered() {
    command -v launchctl >/dev/null 2>&1 || return 1
    launchctl print "gui/$(id -u)/${SERVICE_LABEL_PREFIX}.$1" >/dev/null 2>&1
}
