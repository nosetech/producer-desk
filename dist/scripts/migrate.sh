#!/bin/bash
# 旧バージョンの展開先ディレクトリから、tarballに含まれないユーザー固有の
# 状態ファイル（config/projects.yaml・config/usage.db・config/sessions.json・
# .env・logs/）を新バージョンの展開先ディレクトリ（このスクリプトが置かれている
# scripts/の1階層上）へ引き継ぐマイグレーションツール（issue #155）。
#
# 使い方:
#   cd <新バージョンの展開先ディレクトリ>
#   ./scripts/migrate.sh <旧バージョンの展開先ディレクトリ> [--with-logs] [--force]
#
#   <旧バージョンの展開先ディレクトリ>  移行元。tarball展開直後の、config/・
#                                     .env・logs/等を含むディレクトリ
#   --with-logs                     logs/ ディレクトリも合わせてコピーする
#                                    （省略時は対象外。必須ではない実行ログの
#                                    ため既定ではコピーしない）
#   --force                         新バージョン側に同名ファイルが既に存在する
#                                    場合、既存ファイルを<file>.bak-<timestamp>
#                                    にリネームしてから上書きする（省略時は
#                                    スキップし警告のみ表示、何度実行しても安全）
#
# 対象ファイルと扱い:
#   config/projects.yaml   対象プロジェクト設定。コピー前にPyYAMLでYAMLとして
#                          パース可能か検証する（python3にPyYAMLが無い環境では
#                          検証をスキップする旨を表示した上でコピーする）
#   config/sessions.json   issueごとのClaude CodeセッションID。コピー前にJSONと
#                          してパース可能か検証する（python3標準ライブラリのみ
#                          使用）
#   config/usage.db        利用量・コスト記録。`sqlite3 .backup`でオンライン
#                          バックアップとしてコピーする（新旧プロセスが並行
#                          稼働していても不整合なコピーを作らない）。コピー前に
#                          `PRAGMA user_version`を本スクリプトが期待するスキーマ
#                          バージョン（EXPECTED_USAGE_DB_SCHEMA_VERSION、
#                          orchestrator/orchestrator/usage_store.pyの
#                          SCHEMA_VERSIONと同じ値を保持）と比較し、一致しない
#                          場合は自動移行が未対応であるとしてエラーで停止する。
#                          user_version未設定(0)の場合は、スキーマバージョン
#                          管理導入（issue #155）より前に作成されたDBとみなし
#                          そのままコピーしてよい（テーブル定義は変更されて
#                          いないため）
#   .env                    ユーザー設定（SLACK_WEBHOOK_URL等）
#   logs/                   Agent Runner実行ログ等（--with-logs指定時のみ）
#
# 非スコープ: 旧ディレクトリの削除・アーカイブは行わない（移行後も旧ディレクトリは
# 変更せず残す。新バージョンの動作確認が済むまで旧バージョンを併用できるように
# するため、削除するかどうかは利用者の判断に委ねる）。新バージョン側の起動
# （bin/start.sh）は移行後に利用者自身が行う。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# orchestrator/orchestrator/usage_store.py の SCHEMA_VERSION と同じ値を保つこと。
# 一致しない値のままリリースすると、実際にはコピー不可能なスキーマ変更後の
# usage.dbを誤って「コピー可能」と判定してしまう。
# issue #86でlocal_llm_usage_reportsテーブルを追加したためversion 2へ更新。
EXPECTED_USAGE_DB_SCHEMA_VERSION=2

log() {
    echo "[migrate] $*"
}

err() {
    echo "[migrate] $*" >&2
}

usage() {
    cat <<EOF
使い方: $(basename "$0") <旧バージョンの展開先ディレクトリ> [--with-logs] [--force]

  <旧バージョンの展開先ディレクトリ>  移行元ディレクトリ（config/・.env・logs/
                                    等を含む、tarball展開直後のルート）
  --with-logs                      logs/ ディレクトリも合わせてコピーする
  --force                          新バージョン側の既存ファイルをバックアップの上
                                    上書きする（省略時はスキップ）
EOF
}

if [ "$#" -lt 1 ]; then
    usage
    exit 1
fi

OLD_ROOT_ARG="$1"
shift

WITH_LOGS=0
FORCE=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-logs)
            WITH_LOGS=1
            ;;
        --force)
            FORCE=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            err "不明なオプション: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

if [ ! -d "${OLD_ROOT_ARG}" ]; then
    err "旧バージョンの展開先ディレクトリが見つかりません: ${OLD_ROOT_ARG}"
    exit 1
fi
OLD_ROOT="$(cd "${OLD_ROOT_ARG}" && pwd)"

if [ "${OLD_ROOT}" = "${NEW_ROOT}" ]; then
    err "旧バージョンと新バージョンの展開先ディレクトリが同一です: ${OLD_ROOT}"
    exit 1
fi

log "移行元: ${OLD_ROOT}"
log "移行先: ${NEW_ROOT}"

# ファイルを1件コピーする。新バージョン側に既に存在する場合は、FORCE次第で
# スキップ、またはタイムスタンプ付きでバックアップした上で上書きする。
copy_file() {
    local src="$1"
    local dst="$2"
    local label="$3"

    if [ ! -f "${src}" ]; then
        log "スキップ: ${label}（移行元に存在しません: ${src}）"
        return 0
    fi

    if [ -f "${dst}" ]; then
        if [ "${FORCE}" -ne 1 ]; then
            log "スキップ: ${label}（移行先に既に存在します。上書きする場合は --force を指定: ${dst}）"
            return 0
        fi
        local backup="${dst}.bak-$(date +%Y%m%d-%H%M%S)"
        mv "${dst}" "${backup}"
        log "移行先の既存ファイルをバックアップ: ${backup}"
    fi

    mkdir -p "$(dirname "${dst}")"
    cp "${src}" "${dst}"
    log "コピー完了: ${label} -> ${dst}"
}

# --- config/projects.yaml ---
PROJECTS_SRC="${OLD_ROOT}/config/projects.yaml"
PROJECTS_DST="${NEW_ROOT}/config/projects.yaml"
if [ -f "${PROJECTS_SRC}" ]; then
    if command -v python3 >/dev/null 2>&1 && python3 -c "import yaml" >/dev/null 2>&1; then
        if ! python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding='utf-8'))" "${PROJECTS_SRC}"; then
            err "config/projects.yaml のYAML検証に失敗しました。移行を中止します: ${PROJECTS_SRC}"
            exit 1
        fi
    else
        log "警告: python3のPyYAMLが見つからないため config/projects.yaml の検証をスキップします"
    fi
fi
copy_file "${PROJECTS_SRC}" "${PROJECTS_DST}" "config/projects.yaml"

# --- config/sessions.json ---
SESSIONS_SRC="${OLD_ROOT}/config/sessions.json"
SESSIONS_DST="${NEW_ROOT}/config/sessions.json"
if [ -f "${SESSIONS_SRC}" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3が見つかりません。config/sessions.jsonの検証にはpython3が必要です"
        exit 1
    fi
    if ! python3 -c "import json, sys; json.load(open(sys.argv[1], encoding='utf-8'))" "${SESSIONS_SRC}"; then
        err "config/sessions.json のJSON検証に失敗しました。移行を中止します: ${SESSIONS_SRC}"
        exit 1
    fi
fi
copy_file "${SESSIONS_SRC}" "${SESSIONS_DST}" "config/sessions.json"

# --- config/usage.db ---
USAGE_DB_SRC="${OLD_ROOT}/config/usage.db"
USAGE_DB_DST="${NEW_ROOT}/config/usage.db"
if [ -f "${USAGE_DB_SRC}" ]; then
    if ! command -v sqlite3 >/dev/null 2>&1; then
        err "sqlite3コマンドが見つかりません。config/usage.dbの移行には sqlite3 が必要です"
        exit 1
    fi

    SRC_SCHEMA_VERSION="$(sqlite3 "${USAGE_DB_SRC}" 'PRAGMA user_version;')"
    if [ "${SRC_SCHEMA_VERSION}" != "0" ] && [ "${SRC_SCHEMA_VERSION}" != "${EXPECTED_USAGE_DB_SCHEMA_VERSION}" ]; then
        err "config/usage.db のスキーマバージョン(${SRC_SCHEMA_VERSION})が、本スクリプトが対応するバージョン(${EXPECTED_USAGE_DB_SCHEMA_VERSION})と一致しません。"
        err "このバージョン間の自動移行には対応していません。手動での移行、または対応するバージョンのmigrate.shを使ってください。"
        exit 1
    fi

    if [ -f "${USAGE_DB_DST}" ]; then
        if [ "${FORCE}" -ne 1 ]; then
            log "スキップ: config/usage.db（移行先に既に存在します。上書きする場合は --force を指定: ${USAGE_DB_DST}）"
        else
            backup="${USAGE_DB_DST}.bak-$(date +%Y%m%d-%H%M%S)"
            mv "${USAGE_DB_DST}" "${backup}"
            log "移行先の既存ファイルをバックアップ: ${backup}"
            mkdir -p "$(dirname "${USAGE_DB_DST}")"
            sqlite3 "${USAGE_DB_SRC}" ".backup '${USAGE_DB_DST}'"
            log "コピー完了: config/usage.db -> ${USAGE_DB_DST}"
        fi
    else
        mkdir -p "$(dirname "${USAGE_DB_DST}")"
        sqlite3 "${USAGE_DB_SRC}" ".backup '${USAGE_DB_DST}'"
        log "コピー完了: config/usage.db -> ${USAGE_DB_DST}"
    fi
else
    log "スキップ: config/usage.db（移行元に存在しません: ${USAGE_DB_SRC}）"
fi

# --- .env ---
copy_file "${OLD_ROOT}/.env" "${NEW_ROOT}/.env" ".env"

# --- logs/ ---
if [ "${WITH_LOGS}" -eq 1 ]; then
    LOGS_SRC="${OLD_ROOT}/logs"
    LOGS_DST="${NEW_ROOT}/logs"
    if [ -d "${LOGS_SRC}" ]; then
        mkdir -p "${LOGS_DST}"
        cp -R "${LOGS_SRC}/." "${LOGS_DST}/"
        log "コピー完了: logs/ -> ${LOGS_DST}/"
    else
        log "スキップ: logs/（移行元に存在しません: ${LOGS_SRC}）"
    fi
else
    log "スキップ: logs/（--with-logs 未指定）"
fi

log "移行が完了しました。${NEW_ROOT} で ./bin/start.sh を実行し、ダッシュボードでプロジェクト・利用量履歴が引き継がれていることを確認してください。"
