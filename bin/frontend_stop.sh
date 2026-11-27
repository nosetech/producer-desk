#!/bin/bash
# dashboard（フロントエンド）のみを停止する（issue #326）。bin/start.sh /
# bin/frontend_start.sh のどちらで起動したものも logs/dashboard.pid で止められる。
#
# 使い方:
#   ./bin/frontend_stop.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="frontend_stop"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"

stop_process "dashboard" "${DASHBOARD_PID_FILE}"
