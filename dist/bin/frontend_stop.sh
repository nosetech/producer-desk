#!/bin/bash
# dashboardのみを停止する（配布パッケージ用、issue #326）。bin/start.sh /
# bin/frontend_start.sh のどちらで起動したものも logs/dashboard.pid で止められる。
#
# 使い方:
#   ./bin/frontend_stop.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="frontend_stop"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"

stop_process "dashboard" "${DASHBOARD_PID_FILE}"
