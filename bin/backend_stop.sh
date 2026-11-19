#!/bin/bash
# orchestrator（バックエンド）のみを停止する（issue #326）。bin/start.sh /
# bin/backend_start.sh のどちらで起動したものも logs/orchestrator.pid で止められる。
#
# 使い方:
#   ./bin/backend_stop.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_TAG="backend_stop"
# shellcheck source=proc.sh
source "${SCRIPT_DIR}/proc.sh"

stop_process "orchestrator" "${ORCHESTRATOR_PID_FILE}"
