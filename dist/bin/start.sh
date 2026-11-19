#!/bin/bash
# 配布パッケージ（GitHub Releasesのtarball、SETUP.md参照）内のdashboard・
# orchestratorを一括起動する。git clone前提の開発用bin/start.shとは異なり、
# ビルド済みのdashboard（Next.js standalone出力）・orchestrator（wheel
# インストール済みの仮想環境）をそのまま起動するだけで、npm install/npm run
# build・pip install -e等のソースビルドは一切行わない。
#
# 使い方:
#   ./bin/start.sh
#
# 初回起動時、orchestrator/.venv が無ければ自動的に作成し、同梱の
# orchestrator/dist/*.whl をインストールしてから起動する。
#
# ポート・LAN公開設定・Slack通知等は環境変数で上書きできる。シェルでの
# exportに加えて、展開先ルートに .env（.env.example参照）を作成しておけば
# このスクリプトが起動時に読み込む。
#
#   ORCHESTRATOR_PORT   orchestratorのbindポート（既定: 8787）。dashboardの
#                       接続先（ORCHESTRATOR_URL）はこのポートに自動追従する
#   ORCHESTRATOR_URL    dashboardからorchestratorへの接続先URL（既定:
#                       http://127.0.0.1:${ORCHESTRATOR_PORT}）。dashboardのみ
#                       別ホスト・別ポートのorchestratorに向けたい場合にのみ
#                       明示的に指定する
#   DASHBOARD_PORT      dashboardのbindポート（既定: 3000）
#   LAN_IP              同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#                       そのLAN IPでbindする。未設定時は全インターフェースで
#                       待ち受ける既定動作のまま）
#   TAILSCALE_IP        外出先からTailscale経由でアクセスする場合のみ設定する
#                       （dashboardをそのTailscale IPでbindする。`tailscale ip -4`
#                       で確認できる自機のTailscale IP。LAN_IPとは同時に指定
#                       できない）
#   SLACK_WEBHOOK_URL   判断待ち・レビュー待ち発生時のSlack通知先。未設定の
#                       場合、通知処理は単にスキップされる（起動エラーには
#                       ならない）
#
# 実処理は bin/backend_start.sh（orchestrator）→ bin/frontend_start.sh（dashboard）
# の順に委譲する（issue #326）。個別に起動・停止したい場合はそれらを直接使う。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/backend_start.sh"
"${SCRIPT_DIR}/frontend_start.sh"
