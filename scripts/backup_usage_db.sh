#!/bin/bash
# config/usage.db（利用量・コスト記録用SQLite）の日次バックアップスクリプト。
# 対象環境: macOS（docs/basic-design.md 2-2、CLAUDE.md参照）
#
# 使い方:
#   ./scripts/backup_usage_db.sh
#
# 環境変数:
#   BACKUP_DEST_DIR   バックアップ先ディレクトリ（デフォルト: ~/Backups/producer-desk）
#   BACKUP_RETENTION_DAYS   バックアップの保持世代数（デフォルト: 30）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DB_PATH="${REPO_ROOT}/config/usage.db"
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
