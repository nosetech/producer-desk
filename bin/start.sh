#!/bin/bash
# dashboard・orchestratorを本番相当構成で一括起動する（運用インスタンス専用）。
# 開発用インスタンスを別途並行起動する場合は README「リリース・日常運用」を参照。
#
# 使い方:
#   ./bin/start.sh
#
# 起動のたびにdashboardの依存関係を`npm ci`でpackage-lock.jsonと照合・是正する
# （ネットワークアクセスが発生する。オフライン環境での起動には対応していない）。
#
# ポート・LAN公開設定は環境変数で上書きできる（shellでexportする方法に加えて、
# orchestrator/.env・dashboard/.env（それぞれの.env.example参照）でも指定可能）。
#
#   ORCHESTRATOR_PORT   orchestratorのbindポート（既定: 8787）。dashboardの
#                       接続先（ORCHESTRATOR_URL）はこのポートに自動追従する
#   ORCHESTRATOR_URL    dashboardからorchestratorへの接続先URL（既定:
#                       http://127.0.0.1:${ORCHESTRATOR_PORT}）。dashboard/.env
#                       で明示指定されている場合はそちらが優先される
#   DASHBOARD_PORT      dashboardのbindポート（既定: 3000）
#   LAN_IP              同一LAN内の別端末に公開する場合のみ設定する（dashboardを
#                       `next start --hostname "$LAN_IP"` で起動する。未設定時は
#                       全インターフェースで待ち受ける既定動作のまま）
#   TAILSCALE_IP        外出先からTailscale経由でアクセスする場合のみ設定する
#                       （dashboardを`next start --hostname "$TAILSCALE_IP"`で
#                       起動する。`tailscale ip -4`で確認できる自機のTailscale
#                       IP。LAN_IPとは同時に指定できない）
#   DASHBOARD_PROCESS_NAME     dashboardのps上のプロセス名（既定:
#                       producer-desk-dashboard）。空文字を指定すると上書きせず
#                       next-serverのままにする（issue #332）
#   ORCHESTRATOR_PROCESS_NAME  orchestratorのps上のプロセス名（既定:
#                       producer-desk-orchestrator）。空文字を指定すると上書きせず
#                       pythonのままにする。setproctitle未インストール時は警告のみ
#   ORCHESTRATOR_PYTHON   orchestratorの起動に使うpythonインタプリタ
#            （既定: orchestrator/.venv/bin/python。.venvが無ければこのスクリプトが
#            自動作成する。既にorchestrator/venv/bin/pythonがあればそちらを使う）
#
# logs/orchestrator.logの出力レベルは環境変数 ORCHESTRATOR_ENV で切り替えられる
# が、このスクリプトは明示的に設定しないため常に既定のproduction相当（INFO以上
# のみ出力）で起動する（開発時にDEBUG以上を見たい場合は`python -m
# orchestrator.main`を直接、ORCHESTRATOR_ENV=developmentを指定して起動すること。
# README「ログ出力先ディレクトリの運用方針」参照）。ローテーション保持日数は
# config/projects.yamlのlog_retention_days（既定7日）に従う。
#
# 実処理は bin/backend_start.sh（orchestrator）→ bin/frontend_start.sh（dashboard）
# の順に委譲する（issue #326）。個別に起動・停止したい場合はそれらを直接使う。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/backend_start.sh"
"${SCRIPT_DIR}/frontend_start.sh"
