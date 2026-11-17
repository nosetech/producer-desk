#!/bin/bash
# 配布パッケージ（SETUP.md参照）のorchestrator・dashboardを、macOSの
# launchd（per-user LaunchAgent）で常時起動するための管理スクリプト（issue #318）。
# ログイン中のみ動作する（LaunchDaemonは対象外）。ログイン時の自動起動と、
# プロセスクラッシュ時の自動再起動（KeepAlive、ThrottleIntervalで再起動間隔を
# 抑制）を行う。
#
# 使い方:
#   ./bin/service.sh install     plistを生成・登録して起動する（再実行で設定変更を反映）
#   ./bin/service.sh uninstall   停止して登録解除し、plistを削除する
#   ./bin/service.sh start       停止中のサービスを起動する
#   ./bin/service.sh stop        サービスを停止する（次回ログインまたはstartまで停止）
#   ./bin/service.sh restart     再起動する（.env / projects.yaml の変更反映にも使う）
#   ./bin/service.sh status      登録・稼働状況を表示する
#
# 内部用サブコマンド（launchdまたはテストが使う。通常は直接実行しない）:
#   ./bin/service.sh render-plist <orchestrator|dashboard>   plistを標準出力へ出す
#   ./bin/service.sh run <orchestrator|dashboard>            サービス本体を起動する
#
# launchdは .env を読み込まないため、plistの起動コマンドをこのスクリプトの
# `run` にしている。`run` が bin/start.sh と同じ lib.sh で .env を読み込み、
# 本体のstdout/stderrをログローテータ（orchestrator.log_rotator）へパイプして
# から起動する（ログを日次ローテーションするため、launchdのStandardOutPath
# には直接向けない。issue #114参照）。.envの変更は restart で反映される。
#
# 環境変数:
#   SERVICE_PATH   launchd下のプロセスに渡すPATHを明示する（既定: gh・claude・
#                  nodeのあるディレクトリ+標準パスを自動解決）
#   LAUNCH_AGENTS_DIR  plistの配置先（既定: ~/Library/LaunchAgents）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ORCHESTRATOR_DIR="${ROOT_DIR}/orchestrator"
DASHBOARD_DIR="${ROOT_DIR}/dashboard"
LOG_DIR="${ROOT_DIR}/logs"

SERVICES=(orchestrator dashboard)
THROTTLE_INTERVAL=30

log() {
    echo "[service] $*"
}

err() {
    echo "[service] $*" >&2
}

# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
DOMAIN="gui/$(id -u)"

label_of() { echo "${SERVICE_LABEL_PREFIX}.$1"; }
plist_of() { echo "${LAUNCH_AGENTS_DIR}/$(label_of "$1").plist"; }

check_service_name() {
    case "${1:-}" in
        orchestrator | dashboard) ;;
        *)
            err "サービス名は orchestrator または dashboard を指定してください: '${1:-}'"
            exit 2
            ;;
    esac
}

xml_escape() {
    local s="$1"
    s="${s//&/&amp;}"
    s="${s//</&lt;}"
    s="${s//>/&gt;}"
    printf '%s' "${s}"
}

# launchd下のプロセスに渡すPATH。gh・claude（orchestratorがbareコマンドとして
# 呼ぶ）とnode（dashboard）のあるディレクトリを自動解決する。見つからない場合、
# プロセスは生きているのに何も動かない状態になるため、installを失敗させる。
resolve_service_path() {
    if [ -n "${SERVICE_PATH:-}" ]; then
        printf '%s' "${SERVICE_PATH}"
        return 0
    fi
    local dirs="" cmd bin
    for cmd in gh claude node; do
        if ! bin="$(command -v "${cmd}" 2>/dev/null)"; then
            err "${cmd} コマンドが見つかりません。インストールしてPATHを通してから再実行してください（launchd下では${cmd}が解決できず動作しません）。"
            return 1
        fi
        dirs="${dirs}:$(dirname "${bin}")"
    done
    dirs="${dirs#:}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # 重複を除去（順序は維持）
    printf '%s' "${dirs}" | awk -v RS=: '!seen[$0]++ { out = out (out ? ":" : "") $0 } END { printf "%s", out }'
}

render_plist() {
    local name="$1" path_value
    path_value="$(xml_escape "${SERVICE_PATH_RESOLVED:-$(resolve_service_path)}")"
    local label
    label="$(label_of "${name}")"
    local workdir="${ROOT_DIR}"
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- bin/service.sh install が生成したファイル。手で編集せず install を再実行すること。 -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$(xml_escape "${label}")</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$(xml_escape "${SCRIPT_DIR}/service.sh")</string>
        <string>run</string>
        <string>${name}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$(xml_escape "${workdir}")</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>${THROTTLE_INTERVAL}</integer>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${path_value}</string>
    </dict>
    <!-- 本体の出力は run がログローテータへパイプするため、ここには run 自身の
         起動前エラー（.env/projects.yamlの不備等）だけが出る。本体のログと
         同じパスには向けない（日次ローテーションのrename後も旧fdへ書き続けて
         肥大化するため。issue #114）。 -->
    <key>StandardOutPath</key>
    <string>$(xml_escape "${LOG_DIR}/${name}.launchd.stderr.log")</string>
    <key>StandardErrorPath</key>
    <string>$(xml_escape "${LOG_DIR}/${name}.launchd.stderr.log")</string>
</dict>
</plist>
EOF
}

# 標準入力を日次ローテーション付きで$1へ書き出すローテータ（bin/start.shと同じ）。
start_log_rotator() {
    cd "${ROOT_DIR}" || return 1
    exec nohup "${ORCHESTRATOR_DIR}/.venv/bin/python" -m orchestrator.log_rotator --path "$1" >/dev/null 2>&1
}

# launchdから呼ばれるサービス本体。bin/start.shと同じ設定読み込みを行い、
# 本体へexecする（launchdが本体プロセスを直接監視する）。
run_service() {
    local name="$1"
    mkdir -p "${LOG_DIR}"
    load_config || exit 1
    cd "${ROOT_DIR}"
    case "${name}" in
        orchestrator)
            export PYTHONUNBUFFERED=1
            exec "${ORCHESTRATOR_DIR}/.venv/bin/orchestrator" \
                > >(start_log_rotator "${LOG_DIR}/orchestrator.stderr.log") 2>&1
            ;;
        dashboard)
            cd "${DASHBOARD_DIR}"
            export NODE_ENV=production
            export PORT="${DASHBOARD_PORT}"
            if [ -n "${DASHBOARD_BIND_HOST}" ]; then
                export HOSTNAME="${DASHBOARD_BIND_HOST}"
            fi
            exec node server.js > >(start_log_rotator "${LOG_DIR}/dashboard.log") 2>&1
            ;;
    esac
}

# bin/start.shで手動起動中（PIDファイルのプロセスが生存）なら失敗させる。
check_no_manual_run() {
    local name pid_file pid
    for name in "${SERVICES[@]}"; do
        pid_file="${LOG_DIR}/${name}.pid"
        if [ -f "${pid_file}" ]; then
            pid="$(cat "${pid_file}")"
            if kill -0 "${pid}" 2>/dev/null; then
                err "${name} が bin/start.sh で手動起動中です（PID ${pid}）。先に ./bin/stop.sh で停止してください。"
                exit 1
            fi
        fi
    done
}

require_macos() {
    if [ "$(uname -s)" != "Darwin" ] || ! command -v launchctl >/dev/null 2>&1; then
        err "service.sh はmacOS（launchd）専用です。"
        exit 1
    fi
}

# bootout後はlaunchd側の解除が非同期で、直後のbootstrapが失敗しやすい。解除の
# 完了を待つ。
wait_unregistered() {
    local name="$1"
    for i in $(seq 1 20); do
        launchd_registered "${name}" || return 0
        sleep 0.5
    done
    err "${name} のlaunchd登録解除が完了しませんでした。"
    return 1
}

do_bootout() {
    local name="$1"
    if launchd_registered "${name}"; then
        launchctl bootout "${DOMAIN}/$(label_of "${name}")" >/dev/null 2>&1 || true
        wait_unregistered "${name}"
    fi
}

do_bootstrap() {
    local name="$1"
    local plist
    plist="$(plist_of "${name}")"
    for _ in 1 2 3 4 5; do
        if launchctl bootstrap "${DOMAIN}" "${plist}" 2>/dev/null; then
            return 0
        fi
        # 再登録競合（Input/output error等）は少し待てば通ることが多い
        sleep 1
    done
    err "${name} のlaunchd登録（bootstrap）に失敗しました: ${plist}"
    return 1
}

cmd_install() {
    require_macos
    check_no_manual_run
    mkdir -p "${LOG_DIR}"
    load_config || exit 1
    ensure_orchestrator_venv || exit 1
    if [ ! -f "${DASHBOARD_DIR}/server.js" ]; then
        err "dashboard/server.js が見つかりません。配布パッケージが破損している可能性があります。"
        exit 1
    fi
    SERVICE_PATH_RESOLVED="$(resolve_service_path)" || exit 1
    mkdir -p "${LAUNCH_AGENTS_DIR}"

    local name
    for name in "${SERVICES[@]}"; do
        render_plist "${name}" >"$(plist_of "${name}")"
        do_bootout "${name}"
        do_bootstrap "${name}"
        launchctl enable "${DOMAIN}/$(label_of "${name}")" >/dev/null 2>&1 || true
        log "${name} を登録・起動しました"
    done
    log "PATH: ${SERVICE_PATH_RESOLVED}"
    show_urls
    log "状態確認: ./bin/service.sh status ／ 設定変更の反映: ./bin/service.sh restart"
}

cmd_uninstall() {
    require_macos
    local name
    for name in "${SERVICES[@]}"; do
        do_bootout "${name}"
        rm -f "$(plist_of "${name}")"
        log "${name} を停止し、登録を解除しました"
    done
}

cmd_start() {
    require_macos
    check_no_manual_run
    local name
    for name in "${SERVICES[@]}"; do
        if [ ! -f "$(plist_of "${name}")" ]; then
            err "${name} のplistがありません。先に ./bin/service.sh install を実行してください。"
            exit 1
        fi
        if launchd_registered "${name}"; then
            launchctl kickstart "${DOMAIN}/$(label_of "${name}")" >/dev/null 2>&1 || true
        else
            do_bootstrap "${name}"
        fi
        log "${name} を起動しました"
    done
}

cmd_stop() {
    require_macos
    local name
    for name in "${SERVICES[@]}"; do
        do_bootout "${name}"
        log "${name} を停止しました（./bin/service.sh start で再開）"
    done
}

cmd_restart() {
    require_macos
    check_no_manual_run
    local name
    for name in "${SERVICES[@]}"; do
        if [ ! -f "$(plist_of "${name}")" ]; then
            err "${name} のplistがありません。先に ./bin/service.sh install を実行してください。"
            exit 1
        fi
        if launchd_registered "${name}"; then
            launchctl kickstart -k "${DOMAIN}/$(label_of "${name}")" >/dev/null 2>&1 || true
        else
            do_bootstrap "${name}"
        fi
        log "${name} を再起動しました"
    done
}

show_urls() {
    local port_o="${ORCHESTRATOR_PORT:-8787}" port_d="${DASHBOARD_PORT:-3000}"
    log "  orchestrator URL: http://127.0.0.1:${port_o}"
    log "  dashboard URL:    http://${DASHBOARD_BIND_HOST:-127.0.0.1}:${port_d}"
    log "  ログ: ${LOG_DIR}/orchestrator.log, ${LOG_DIR}/dashboard.log"
}

cmd_status() {
    require_macos
    local name out state pid
    for name in "${SERVICES[@]}"; do
        if ! launchd_registered "${name}"; then
            if [ -f "$(plist_of "${name}")" ]; then
                log "${name}: 停止中（plist配置済み・未登録。./bin/service.sh start で起動）"
            else
                log "${name}: 未インストール"
            fi
            continue
        fi
        out="$(launchctl print "${DOMAIN}/$(label_of "${name}")" 2>/dev/null || true)"
        state="$(printf '%s\n' "${out}" | awk '/^[[:space:]]*state = /{print $3; exit}')"
        pid="$(printf '%s\n' "${out}" | awk '/^[[:space:]]*pid = /{print $3; exit}')"
        log "${name}: 登録済み state=${state:-unknown}${pid:+ pid=${pid}}"
    done
}

main() {
    local cmd="${1:-}"
    case "${cmd}" in
        install) cmd_install ;;
        uninstall) cmd_uninstall ;;
        start) cmd_start ;;
        stop) cmd_stop ;;
        restart) cmd_restart ;;
        status) cmd_status ;;
        render-plist)
            check_service_name "${2:-}"
            render_plist "$2"
            ;;
        run)
            check_service_name "${2:-}"
            run_service "$2"
            ;;
        *)
            err "使い方: $0 {install|uninstall|start|stop|restart|status}"
            exit 2
            ;;
    esac
}

main "$@"
