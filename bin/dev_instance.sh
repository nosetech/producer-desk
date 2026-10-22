#!/bin/bash
# 動作確認用のorchestrator・dashboardを、運用インスタンスと分離して起動・停止する
# （開発者・Agent Runner向け。配布tarball（dist/）には含めない）。
#
# 使い方:
#   ./bin/dev_instance.sh start
#   ./bin/dev_instance.sh stop
#   ./bin/dev_instance.sh status
#
# 「名前やポートでプロセスを探して止める」(pkill / killall / lsofの結果をkill等)
# と、運用インスタンスや他worktreeのインスタンスまで巻き込んで停止しうる。
# このスクリプトは、自分が起動したプロセスグループをworktree内の.dev-run/に記録し、
# stopではその記録に一致するものだけを止める。名前・ポートからの検索は行わない。
#
# start:
#   - orchestrator / dashboardをそれぞれ新しいセッション（プロセスグループ）で
#     起動する（macOSにはsetsidが無いためpython3のos.setsid()で代替する）。npm→
#     next-serverなどの子孫も同一PGIDにまとまる。
#   - ポートは18000番台から空きを自動採番する。DEV_ORCHESTRATOR_PORT /
#     DEV_DASHBOARD_PORT で明示指定する場合も、既定値（8787/3000）や使用中のポート
#     は拒否する。運用インスタンスから継承した環境変数ORCHESTRATOR_PORT /
#     DASHBOARD_PORT / ORCHESTRATOR_URLは参照せず、起動する子プロセスには採番した
#     値で上書きして渡す。
#   - dashboardのORCHESTRATOR_URLは採番したorchestratorポートに自動で合わせる。
#   - PROJECTS_CONFIG_PATH / SESSIONS_PATH等は.dev-run/配下の開発用ファイルを既定
#     にする（環境変数で明示した場合はそちらを使う）。
#   - dashboardはnode_modulesが必要（無ければエラー終了する。dashboardで`npm ci`
#     を実行しておくこと）。
#
# stop:
#   記録したPIDが生存し、PGIDが記録と一致し、かつ起動時にプロセスへ付与した目印
#   （環境変数 PRODUCER_DESK_DEV_INSTANCE）がこのworktreeのものと一致する場合のみ
#   `kill -- -<PGID>`でグループごとSIGTERM、残れば同グループにSIGKILLする。
#   1つでも不一致ならkillせずエラー終了する（PID再利用・記録の改ざんの検出）。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ORCHESTRATOR_DIR="${REPO_ROOT}/orchestrator"
DASHBOARD_DIR="${REPO_ROOT}/dashboard"
DEV_DIR="${REPO_ROOT}/.dev-run"

PRODUCTION_ORCHESTRATOR_PORT=8787
PRODUCTION_DASHBOARD_PORT=3000
PORT_SEARCH_START=18000
PORT_SEARCH_END=18999

# 起動したプロセスに付与する目印の環境変数名。stopでps経由で読み戻し、このworktreeの
# 記録と一致するか確認する。
MARKER_ENV="PRODUCER_DESK_DEV_INSTANCE"

log() {
    echo "[dev_instance] $*"
}

err() {
    echo "[dev_instance] $*" >&2
}

usage() {
    err "使い方: $0 start|stop|status"
    exit 2
}

record_file() {
    echo "${DEV_DIR}/$1.$2"
}

# ポートがlistenされていないか確認する（0: 空き）。
port_is_free() {
    python3 -I -c '
import socket, sys
port = int(sys.argv[1])
for host in ("127.0.0.1", "0.0.0.0"):
    s = socket.socket()
    try:
        s.bind((host, port))
    except OSError:
        sys.exit(1)
    finally:
        s.close()
' "$1"
}

find_free_port() {
    local port exclude="$1"
    for port in $(seq "${PORT_SEARCH_START}" "${PORT_SEARCH_END}"); do
        [ "${port}" = "${exclude}" ] && continue
        if port_is_free "${port}"; then
            echo "${port}"
            return 0
        fi
    done
    return 1
}

# 明示指定されたポートを検証する。既定値・使用中・数値でない場合は拒否する。
validate_explicit_port() {
    local name="$1" port="$2" production_port="$3"
    case "${port}" in
    '' | *[!0-9]*)
        err "${name}=${port} は数値ではありません。"
        return 1
        ;;
    esac
    if [ "${port}" = "${production_port}" ]; then
        err "${name}=${port} は運用インスタンスの既定ポートです。起動を拒否します（未指定にすれば空きポートを自動採番します）。"
        return 1
    fi
    if ! port_is_free "${port}"; then
        err "${name}=${port} は既に使用中です。起動を拒否します。"
        return 1
    fi
}

# PIDが生存していて、PGIDが記録と一致し、目印がこのworktreeのものか確認する。
# 失敗時は理由を標準エラーに出して1を返す（killしない）。
verify_instance() {
    local name="$1" pid="$2" pgid="$3" marker="$4"

    if ! kill -0 "${pid}" 2>/dev/null; then
        err "${name}: 記録したPID ${pid} のプロセスは存在しません。"
        return 1
    fi
    local actual_pgid
    actual_pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ')"
    if [ "${actual_pgid}" != "${pgid}" ]; then
        err "${name}: PID ${pid} のPGID（${actual_pgid:-不明}）が記録（${pgid}）と一致しません。PIDが再利用された可能性があるためkillしません。"
        return 1
    fi
    # PGIDが自分自身・init・0等の場合は絶対に撃たない。
    local own_pgid
    own_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
    if [ "${pgid}" -le 1 ] || [ "${pgid}" = "${own_pgid}" ]; then
        err "${name}: 記録したPGID ${pgid} は停止対象にできません。"
        return 1
    fi
    # ps eww はプロセスの環境変数を表示する。起動時に付与した目印が無い、または
    # 別worktreeのものであれば拒否する。
    if ! ps eww -o command= -p "${pid}" 2>/dev/null | tr ' ' '\n' | grep -qxF "${MARKER_ENV}=${marker}"; then
        err "${name}: PID ${pid} は このworktree（${REPO_ROOT}）の開発インスタンスとして起動されたプロセスではありません。killしません。"
        return 1
    fi
}

# 新しいセッションでコマンドを起動し、PID（=PGID）を記録する。
# $1=名前 $2=cwd $3=ログ 以降=コマンド
launch() {
    local name="$1" cwd="$2" logfile="$3"
    shift 3
    local marker="${DEV_DIR}/${name}"
    (
        cd "${cwd}" || exit 1
        export "${MARKER_ENV}=${marker}"
        nohup python3 -I -c '
import os, sys
os.setsid()
os.execvp(sys.argv[1], sys.argv[1:])
' "$@" >>"${logfile}" 2>&1 &
        echo $! >"$(record_file "${name}" pid)"
    )
    local pid
    pid="$(cat "$(record_file "${name}" pid)")"
    # setsid後はPID==PGID。ps上でも確認して記録する。
    sleep 0.5
    local pgid
    pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ')"
    if [ -z "${pgid}" ]; then
        err "${name} の起動に失敗しました。ログを確認してください: ${logfile}（orchestratorは${REPO_ROOT}/logs/orchestrator.logにも出力します）"
        cleanup_records "${name}"
        return 1
    fi
    echo "${pgid}" >"$(record_file "${name}" pgid)"
    echo "${marker}" >"$(record_file "${name}" marker)"
    echo "${cwd}" >"$(record_file "${name}" cwd)"
}

cleanup_records() {
    rm -f "$(record_file "$1" pid)" "$(record_file "$1" pgid)" "$(record_file "$1" marker)" "$(record_file "$1" cwd)"
}

cmd_start() {
    mkdir -p "${DEV_DIR}"

    local name
    for name in orchestrator dashboard; do
        if [ -f "$(record_file "${name}" pid)" ]; then
            local pid
            pid="$(cat "$(record_file "${name}" pid)")"
            if kill -0 "${pid}" 2>/dev/null; then
                err "${name} は既に起動中です（PID ${pid}）。先に $0 stop を実行してください。"
                return 1
            fi
            err "${name} の古い記録を検出しました（PID ${pid} は存在しません）。削除して続行します。"
            cleanup_records "${name}"
        fi
    done

    local orch_port dash_port
    if [ -n "${DEV_ORCHESTRATOR_PORT:-}" ]; then
        validate_explicit_port DEV_ORCHESTRATOR_PORT "${DEV_ORCHESTRATOR_PORT}" "${PRODUCTION_ORCHESTRATOR_PORT}" || return 1
        orch_port="${DEV_ORCHESTRATOR_PORT}"
    else
        orch_port="$(find_free_port "")" || {
            err "空きポートが見つかりません。"
            return 1
        }
    fi
    if [ -n "${DEV_DASHBOARD_PORT:-}" ]; then
        validate_explicit_port DEV_DASHBOARD_PORT "${DEV_DASHBOARD_PORT}" "${PRODUCTION_DASHBOARD_PORT}" || return 1
        dash_port="${DEV_DASHBOARD_PORT}"
    else
        dash_port="$(find_free_port "${orch_port}")" || {
            err "空きポートが見つかりません。"
            return 1
        }
    fi
    if [ "${orch_port}" = "${dash_port}" ]; then
        err "DEV_ORCHESTRATOR_PORT と DEV_DASHBOARD_PORT が同じです（${orch_port}）。"
        return 1
    fi

    local next_bin="${DASHBOARD_DIR}/node_modules/.bin/next"
    if [ ! -x "${next_bin}" ]; then
        err "dashboard/node_modules/.bin/next が見つかりません。dashboardで npm ci を実行してください。"
        return 1
    fi

    local python="${ORCHESTRATOR_PYTHON:-}"
    if [ -z "${python}" ]; then
        if [ -x "${ORCHESTRATOR_DIR}/.venv/bin/python" ]; then
            python="${ORCHESTRATOR_DIR}/.venv/bin/python"
        elif [ -x "${ORCHESTRATOR_DIR}/venv/bin/python" ]; then
            python="${ORCHESTRATOR_DIR}/venv/bin/python"
        else
            python="python3"
        fi
    fi

    # 運用インスタンスの実データと混ざらないよう、開発用ファイルを既定にする。
    export PROJECTS_CONFIG_PATH="${PROJECTS_CONFIG_PATH:-${DEV_DIR}/projects.yaml}"
    export SESSIONS_PATH="${SESSIONS_PATH:-${DEV_DIR}/sessions.json}"
    export EXECUTION_OVERRIDES_PATH="${EXECUTION_OVERRIDES_PATH:-${DEV_DIR}/execution_overrides.json}"
    export ORCHESTRATOR_PROMPTS_PATH="${ORCHESTRATOR_PROMPTS_PATH:-${DEV_DIR}/prompts.yaml}"
    if [ ! -f "${PROJECTS_CONFIG_PATH}" ] && [ "${PROJECTS_CONFIG_PATH}" = "${DEV_DIR}/projects.yaml" ]; then
        # 運用中の実プロジェクトを含めない（同一worktreeへの同時ディスパッチ防止）。
        # orchestratorは起動時に1件以上のプロジェクトを要求するため、実在しない
        # ダミーのリポジトリを1件だけ登録する（ポーリングはエラーログになるだけで無害）。
        mkdir -p "${DEV_DIR}/placeholder-worktree"
        printf 'projects:\n  - repo: nosetech/dev-instance-placeholder\n    worktree_path: %s\n' \
            "${DEV_DIR}/placeholder-worktree" >"${PROJECTS_CONFIG_PATH}"
        log "対象プロジェクトを含まない開発用設定を作成しました: ${PROJECTS_CONFIG_PATH}"
    fi

    log "orchestrator を起動します（ポート${orch_port}）..."
    ORCHESTRATOR_PORT="${orch_port}" launch orchestrator "${ORCHESTRATOR_DIR}" "${DEV_DIR}/orchestrator.log" \
        "${python}" -m orchestrator.main || return 1

    log "dashboard を起動します（ポート${dash_port}）..."
    if ! ORCHESTRATOR_URL="http://127.0.0.1:${orch_port}" launch dashboard "${DASHBOARD_DIR}" "${DEV_DIR}/dashboard.log" \
        "${next_bin}" dev -p "${dash_port}"; then
        err "dashboard の起動に失敗したため orchestrator も停止します。"
        cmd_stop
        return 1
    fi

    echo "${orch_port}" >"${DEV_DIR}/orchestrator.port"
    echo "${dash_port}" >"${DEV_DIR}/dashboard.port"

    log "起動完了"
    log "  orchestrator: http://127.0.0.1:${orch_port}  (PID $(cat "$(record_file orchestrator pid)"))  log: ${DEV_DIR}/orchestrator.log"
    log "  dashboard:    http://127.0.0.1:${dash_port}  (PID $(cat "$(record_file dashboard pid)"))  log: ${DEV_DIR}/dashboard.log"
    log "停止する場合は $0 stop を実行してください（pkill等で止めないこと）。"
}

# 1つのインスタンスを停止する。記録が無ければ0、安全確認に失敗すれば1を返す。
stop_instance() {
    local name="$1"
    local pid_file pgid_file marker_file
    pid_file="$(record_file "${name}" pid)"
    pgid_file="$(record_file "${name}" pgid)"
    marker_file="$(record_file "${name}" marker)"

    if [ ! -f "${pid_file}" ]; then
        log "${name}: 記録がありません（起動していません）。"
        return 0
    fi
    if [ ! -f "${pgid_file}" ] || [ ! -f "${marker_file}" ]; then
        err "${name}: 記録が不完全です。killしません。${DEV_DIR} を確認してください。"
        return 1
    fi

    local pid pgid marker
    pid="$(cat "${pid_file}")"
    pgid="$(cat "${pgid_file}")"
    marker="$(cat "${marker_file}")"
    case "${pid}${pgid}" in
    '' | *[!0-9]*)
        err "${name}: 記録の内容が不正です。killしません。"
        return 1
        ;;
    esac
    # 記録された目印は、このworktreeの.dev-run/配下の自分の名前でなければならない。
    if [ "${marker}" != "${DEV_DIR}/${name}" ]; then
        err "${name}: 記録の目印（${marker}）がこのworktreeのものと一致しません。killしません。"
        return 1
    fi

    if ! kill -0 "${pid}" 2>/dev/null; then
        log "${name}: プロセス（PID ${pid}）は既に存在しません。記録を削除します。"
        cleanup_records "${name}"
        return 0
    fi

    verify_instance "${name}" "${pid}" "${pgid}" "${marker}" || return 1

    log "${name} を停止します（PID ${pid} / PGID ${pgid}）..."
    kill -TERM -- "-${pgid}" 2>/dev/null || true
    local _
    for _ in $(seq 1 20); do
        kill -0 -- "-${pgid}" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 -- "-${pgid}" 2>/dev/null; then
        err "${name}（PGID ${pgid}）が停止しなかったため強制終了します"
        kill -KILL -- "-${pgid}" 2>/dev/null || true
    fi
    cleanup_records "${name}"
    rm -f "${DEV_DIR}/${name}.port"
    log "${name} を停止しました"
}

cmd_stop() {
    local status=0
    # dashboard→orchestratorの順で止める。片方が失敗しても他方は続行する。
    stop_instance dashboard || status=1
    stop_instance orchestrator || status=1
    return "${status}"
}

cmd_status() {
    local name any=1
    for name in orchestrator dashboard; do
        if [ -f "$(record_file "${name}" pid)" ]; then
            local pid
            pid="$(cat "$(record_file "${name}" pid)")"
            if kill -0 "${pid}" 2>/dev/null; then
                log "${name}: 起動中（PID ${pid}、ポート $(cat "${DEV_DIR}/${name}.port" 2>/dev/null || echo 不明)）"
                any=0
            else
                log "${name}: 記録あり・プロセスなし（PID ${pid}）"
            fi
        else
            log "${name}: 停止中"
        fi
    done
    return "${any}"
}

[ "$#" -eq 1 ] || usage
case "$1" in
start) cmd_start ;;
stop) cmd_stop ;;
status) cmd_status ;;
*) usage ;;
esac
