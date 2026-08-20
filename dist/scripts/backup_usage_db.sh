#!/bin/bash
# config/usage.db（利用量・コスト記録用SQLite）の日次バックアップスクリプト。
# 対象環境: macOS（配布パッケージ展開後はSETUP.md、git clone開発環境では
# CONTRIBUTING.mdの「DBバックアップ（macOS launchd）」参照。このリポジトリ内では
# dist/scripts/配下が唯一の実体で、リリース時にtarballの展開先ルート直下scripts/
# として同梱される。docs/basic-design.md 7章参照）。
#
# 使い方:
#   ./scripts/backup_usage_db.sh
#
# 環境変数:
#   BACKUP_DEST_DIR   バックアップ先ディレクトリ（デフォルト: ~/Backups/producer-desk）
#   BACKUP_RETENTION_DAYS   バックアップの保持世代数（デフォルト: 30）
#   USAGE_DB_PATH     config/usage.dbのパス（省略時は下記参照）
#
# config/usage.dbの既定パスは、USAGE_DB_PATH未設定時、このスクリプト自身の
# 1階層上=ROOT_DIRを基準に解決する。展開済みtarball内（scripts/backup_usage_db.sh）
# ではROOT_DIRが展開先ルートと一致するためそのままでよいが、git clone環境で
# このファイルをdist/scripts/backup_usage_db.shとして直接実行する場合はROOT_DIRが
# dist/になってしまうため、環境変数USAGE_DB_PATHでリポジトリルートのconfig/usage.db
# を明示的に指定すること。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DB_PATH="${USAGE_DB_PATH:-${ROOT_DIR}/config/usage.db}"
DEST_DIR="${BACKUP_DEST_DIR:-${HOME}/Backups/producer-desk}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

if [ ! -f "${DB_PATH}" ]; then
    echo "[backup_usage_db] ${DB_PATH} が存在しないためスキップします（初回起動前等）"
    exit 0
fi

mkdir -p "${DEST_DIR}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEST_PATH="${DEST_DIR}/usage-${TIMESTAMP}.db"

# 単純なcpではなくSQLiteのオンラインバックアップAPIを使う。
# オーケストレータ実行中の書き込みと競合しても不整合なコピーを作らない。
sqlite3 "${DB_PATH}" ".backup '${DEST_PATH}'"

echo "[backup_usage_db] バックアップ作成: ${DEST_PATH}"

# 世代管理: 保持日数を超えた古いバックアップを削除する
find "${DEST_DIR}" -maxdepth 1 -name 'usage-*.db' -mtime "+${RETENTION_DAYS}" -print -delete | while read -r removed; do
    echo "[backup_usage_db] 古いバックアップを削除: ${removed}"
done

echo "[backup_usage_db] 完了"
