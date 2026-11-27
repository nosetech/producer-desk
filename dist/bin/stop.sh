#!/bin/bash
# bin/start.sh で起動したdashboard・orchestratorを停止する（配布パッケージ用、
# SETUP.md参照）。
#
# 使い方:
#   ./bin/stop.sh
#
# 実処理は bin/frontend_stop.sh（dashboard）→ bin/backend_stop.sh（orchestrator）
# の順に委譲する（issue #326）。片方が失敗してももう片方は停止を試み、いずれかが
# 失敗していれば非0で終了する。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

status=0
"${SCRIPT_DIR}/frontend_stop.sh" || status=1
"${SCRIPT_DIR}/backend_stop.sh" || status=1

exit "${status}"
